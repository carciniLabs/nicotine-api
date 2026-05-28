import express from 'express';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const port = 3090;

app.use(express.json());

// State management
let pythonReady = false;
let lastStatus = {};
let lastDownloads = [];
let lastShares = [];
const pendingAcks = []; // queue of { res, query, timeout }
const pendingCancelAcks = new Map(); // id -> { res, completed, timeout }
const pendingRescanAck = { res: null, completed: true, timeout: null }; // rescan ack tracker
const searchesByToken = new Map(); // token -> { res, query, results, timeout }

// Reconnection state
let shuttingDown = false;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;
const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 5000;

// Spawn Python bridge
const pythonPath = 'python3';
const bridgeScript = path.join(__dirname, 'bridge.py');
let py;
let buffer = '';

function spawnBridge() {
    py = spawn(pythonPath, [bridgeScript]);
    buffer = '';

    py.stdout.on('data', (data) => {
        buffer += data.toString();
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
            if (!line.trim()) continue;
            try {
                const msg = JSON.parse(line);
                handlePythonMessage(msg);
            } catch (e) {
                // Probably Nicotine debug logs, ignore or log to debug
            }
        }
    });

    py.stderr.on('data', (data) => {
        console.error('Python Stderr:', data.toString());
    });

    py.on('exit', (code) => {
        console.log(`Python bridge exited with code ${code}`);
        pythonReady = false;
        reconnectBridge();
    });
}

function reconnectBridge() {
    // Intentional shutdown (SIGTERM) sets a flag — don't reconnect
    if (shuttingDown) {
        console.log('Bridge exited during shutdown, not reconnecting.');
        return;
    }

    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        console.error(`Max reconnection attempts (${MAX_RECONNECT_ATTEMPTS}) reached. Giving up.`);
        return;
    }

    reconnectAttempts++;
    const backoff = Math.min(INITIAL_BACKOFF_MS * Math.pow(2, reconnectAttempts - 1), MAX_BACKOFF_MS);
    console.log(`Reconnecting bridge in ${backoff}ms (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);

    setTimeout(() => {
        // Clear stale state on reconnect
        searchesByToken.clear();
        pendingAcks.length = 0;
        pendingCancelAcks.clear();
        lastStatus = {};
        lastDownloads = [];
        lastShares = [];

        // Reset rescan ack if pending
        if (pendingRescanAck.res && !pendingRescanAck.completed) {
            pendingRescanAck.completed = true;
            clearTimeout(pendingRescanAck.timeout);
            try {
                pendingRescanAck.res.status(503).json({ error: 'Bridge disconnected, reconnecting' });
            } catch (e) { /* response already sent */ }
            pendingRescanAck.res = null;
        }

        // Fail any pending search HTTP responses that are still waiting
        for (const ack of pendingAcks) {
            if (!ack.completed) {
                ack.completed = true;
                try {
                    ack.res.status(503).json({ error: 'Bridge disconnected, reconnecting' });
                } catch (e) { /* response already sent */ }
            }
        }
        pendingAcks.length = 0;

        // Cancel pending cancel acks
        for (const [id, ctx] of pendingCancelAcks) {
            if (!ctx.completed) {
                ctx.completed = true;
                clearTimeout(ctx.timeout);
                try {
                    ctx.res.status(503).json({ error: 'Bridge disconnected, reconnecting' });
                } catch (e) { /* response already sent */ }
            }
        }
        pendingCancelAcks.clear();

        console.log('Spawning new bridge process...');
        spawnBridge();
    }, backoff);
}

spawnBridge();

function handlePythonMessage(msg) {
    switch (msg.type) {
        case 'ready':
            pythonReady = true;
            reconnectAttempts = 0;  // Reset backoff on successful connection
            console.log('Python bridge ready');
            break;
        case 'connected':
            lastStatus.connected = true;
            lastStatus.username = msg.username || lastStatus.username;
            console.log(`Connected to Soulseek as ${msg.username}`);
            break;
        case 'disconnected':
            lastStatus.connected = false;
            console.log('Disconnected from Soulseek');
            break;
        case 'search_ack':
            const ack = pendingAcks.shift();
            if (ack) {
                console.log(`Search ACK: ${ack.query} -> Token ${msg.token}`);
                // Keep ack.results reference so pushes to searchesByToken also
                // update the ctx that the timeout will read from
                ack.token = msg.token;
                searchesByToken.set(msg.token, ack);
            }
            break;
        case 'search_results':
            const search = searchesByToken.get(msg.token);
            if (search) {
                search.results.push(...msg.data);
                console.log(`Search results: token=${msg.token}, batch=${msg.data.length}, total=${search.results.length}`);
            } else {
                console.log(`Search results for unknown token: ${msg.token}, searchesByToken keys: ${[...searchesByToken.keys()]}`);
            }
            break;
        case 'status':
            lastStatus = msg.data;
            break;
        case 'downloads':
            lastDownloads = msg.data;
            break;
        case 'cancel_download_ack':
            const cancelCtx = pendingCancelAcks.get(msg.id);
            if (cancelCtx && !cancelCtx.completed) {
                cancelCtx.completed = true;
                clearTimeout(cancelCtx.timeout);
                pendingCancelAcks.delete(msg.id);
                if (msg.error) {
                    cancelCtx.res.status(404).json({ error: msg.error, id: msg.id });
                } else {
                    cancelCtx.res.json({ success: true, id: msg.id, user: msg.user, filename: msg.filename });
                }
            }
            break;
        case 'shares':
            lastShares = msg.data;
            break;
        case 'rescan_ack':
            if (pendingRescanAck.res && !pendingRescanAck.completed) {
                pendingRescanAck.completed = true;
                clearTimeout(pendingRescanAck.timeout);
                pendingRescanAck.res.json({ success: true, status: 'rescan_started' });
                pendingRescanAck.res = null;
            }
            break;
        case 'error':
            console.error('Bridge Error:', msg.message);
            break;
    }
}

function sendToPython(cmd) {
    if (!py.stdin.writable) return false;
    py.stdin.write(JSON.stringify(cmd) + '\n');
    return true;
}

// Endpoints

app.get('/status', (req, res) => {
    sendToPython({ method: 'status' });
    setTimeout(() => {
        res.json({
            connected: pythonReady && (lastStatus.connected || false),
            username: lastStatus.username || null,
            server: lastStatus.server || null,
            listening_port: lastStatus.listening_port || 0,
            shares_count: lastStatus.shares || 0,
            downloads_dir: lastStatus.downloads_dir || null,
            uptime: process.uptime()
        });
    }, 250);
});

app.post('/search', (req, res) => {
    const { query, timeout = 20000, max_results = 50 } = req.body;
    if (!query) return res.status(400).json({ error: 'Query required' });
    
    if (!pythonReady) return res.status(503).json({ error: 'Bridge not ready' });

    console.log(`Search request: "${query}"`);
    const ctx = { query, res, results: [], completed: false };
    pendingAcks.push(ctx);
    sendToPython({ method: 'search', params: { query } });
    
    setTimeout(() => {
        if (ctx.completed) return;
        ctx.completed = true;
        if (ctx.token) searchesByToken.delete(ctx.token);
        
        const idx = pendingAcks.indexOf(ctx);
        if (idx > -1) pendingAcks.splice(idx, 1);

        res.json({
            query,
            results: ctx.results.slice(0, max_results),
            total_results: ctx.results.length
        });
    }, timeout);
});

app.post('/download', (req, res) => {
    const { user, file, filename } = req.body;
    const target = file || filename;
    if (!user || !target) return res.status(400).json({ error: 'User and file required' });

    sendToPython({ method: 'download', params: { user, filename: target } });
    res.json({ success: true, status: 'queued' });
});

app.get('/downloads', (req, res) => {
    sendToPython({ method: 'downloads' });
    setTimeout(() => {
        res.json({ downloads: lastDownloads });
    }, 250);
});

// DELETE /download/:id — Cancel a download by transfer ID
app.delete('/download/:id', (req, res) => {
    const { id } = req.params;
    if (!id) return res.status(400).json({ error: 'Transfer ID required' });

    const ctx = { res, completed: false };
    pendingCancelAcks.set(id, ctx);
    sendToPython({ method: 'cancel_download', params: { id } });

    // Timeout fallback
    ctx.timeout = setTimeout(() => {
        if (!ctx.completed) {
            ctx.completed = true;
            pendingCancelAcks.delete(id);
            res.status(504).json({ error: 'Cancel request timed out' });
        }
    }, 5000);
});

// GET /shares — List configured shared folders
app.get('/shares', (req, res) => {
    sendToPython({ method: 'shares' });
    setTimeout(() => {
        res.json({ shares: lastShares });
    }, 250);
});

app.post('/rescan-shares', (req, res) => {
    if (!pythonReady) return res.status(503).json({ error: 'Bridge not ready' });
    
    pendingRescanAck.res = res;
    pendingRescanAck.completed = false;
    sendToPython({ method: 'rescan' });
    
    // Timeout fallback if bridge never sends rescan_ack
    pendingRescanAck.timeout = setTimeout(() => {
        if (!pendingRescanAck.completed) {
            pendingRescanAck.completed = true;
            pendingRescanAck.res = null;
            res.json({ success: true, status: 'rescan_requested', note: 'ack not received within timeout' });
        }
    }, 5000);
});

// Global error handler — prevents raw HTML stack traces on unhandled errors
app.use((err, req, res, next) => {
    console.error('Unhandled error:', err);
    res.status(500).json({ error: err.message || 'Internal server error' });
});

app.listen(port, () => {
    console.log(`Nicotine API listening at http://localhost:${port}`);
});

process.on('SIGTERM', () => {
    shuttingDown = true;
    sendToPython({ method: 'exit' });
    setTimeout(() => process.exit(0), 500);
});