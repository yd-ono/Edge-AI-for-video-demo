const express = require('express');
const WebSocket = require('ws');
const { Kafka, logLevel } = require('kafkajs');
const path = require('path');

const app = express();

// 環境変数から設定を取得
const PORT = process.env.PORT || 8000;
const WS_PORT = process.env.WS_PORT || 8081;
const KAFKA_BROKERS = (process.env.KAFKA_BROKERS || 'localhost:9092').split(',');
const TOPIC_DATA_MESH = process.env.TOPIC_DATA_MESH || 'data-mesh';
const TOPIC_CLIP = process.env.TOPIC_CLIP || 'clip';
const TOPIC_PIDOG = process.env.TOPIC_PIDOG || 'pidog';
const KAFKA_DATAMESH_GROUP_ID = process.env.KAFKA_DATAMESH_GROUP_ID || 'data-mesh-division';
const KAFKA_CLIP_GROUP_ID = process.env.KAFKA_CLIP_GROUP_ID || 'clip-division';
const ALERT_STRING = process.env.ALERT_STRING || 'soldier';
const ALERT_SCORE = parseFloat(process.env.ALERT_SCORE) || 0.5;

// Kafka設定
const kafka = new Kafka({ brokers: KAFKA_BROKERS, logLevel: logLevel.ERROR });
const producer = kafka.producer();
const consumerCLIP = kafka.consumer({ groupId: KAFKA_CLIP_GROUP_ID });
const consumerDATA_MESH = kafka.consumer({ groupId: KAFKA_DATAMESH_GROUP_ID });

// 静的ファイルのホスティング
app.use(express.static(path.join(__dirname, 'public')));

// HTTPサーバの起動
const server = app.listen(PORT, () => {
    console.log(`HTTP Server running at http://0.0.0.0:${PORT}`);
});

// WebSocketサーバの起動
const wss = new WebSocket.Server({ port: WS_PORT });
console.log(`WebSocket Server running at ws://0.0.0.0:${WS_PORT}`);

// WebSocket接続クライアントの管理
const clients = new Set();
wss.on('connection', (ws) => {
    clients.add(ws);
    console.log('WebSocket connected. Clients:', clients.size);

    ws.on('message', async (message) => {
        try {
            const data = JSON.parse(message);
            if (data.topic === TOPIC_PIDOG && data.action) {
                await producer.send({
                    topic: TOPIC_PIDOG,
                    messages: [{ value: JSON.stringify({ actions: data.action, timestamp: Date.now() }) }]
                });
                console.log(`Published to ${TOPIC_PIDOG}:`, data.action);
            } else {
                console.warn('Unknown message format or topic');
            }
        } catch (err) {
            console.error('WebSocket message handling error:', err);
        }
    });

    ws.on('close', () => {
        clients.delete(ws);
        console.log('WebSocket disconnected. Clients:', clients.size);
    });
});

// Kafka Producer の接続
(async () => {
    await producer.connect();
    console.log('Kafka Producer connected');
})();

// Kafka Consumer for DATA_MESH
(async () => {
    await consumerDATA_MESH.connect();
    await consumerDATA_MESH.subscribe({ topic: TOPIC_DATA_MESH, fromBeginning: false });
    await consumerDATA_MESH.run({
        eachMessage: async ({ message }) => {
            try {
                if (!message.value) return;
                const data = JSON.parse(message.value.toString('utf8'));
                const payload = JSON.stringify(data);
                for (const client of clients) {
                    if (client.readyState === WebSocket.OPEN) {
                        client.send(payload);
                    }
                }
            } catch (error) {
                console.error('Error processing DATA_MESH message:', error);
            }
        }
    });
})();

// Kafka Consumer for CLIP
(async () => {
    await consumerCLIP.connect();
    await consumerCLIP.subscribe({ topic: TOPIC_CLIP, fromBeginning: false });
    await consumerCLIP.run({
        eachMessage: async ({ message }) => {
            try {
                if (!message.value) return;
                const data = JSON.parse(message.value.toString('utf8'));
                const labels = Array.isArray(data.labels) ? data.labels : [];
                const suspicious = labels.find(label =>
                    label.name === ALERT_STRING &&
                    typeof label.score === 'number' &&
                    label.score >= ALERT_SCORE
                );

                const payload = JSON.stringify(suspicious ? {
                    alert: true,
                    label: suspicious.name,
                    score: suspicious.score,
                    original: data
                } : {
                    alert: false,
                    original: data
                });

                for (const client of clients) {
                    if (client.readyState === WebSocket.OPEN) {
                        client.send(payload);
                    }
                }
            } catch (err) {
                console.error('[Kafka] Error processing CLIP message:', err);
            }
        }
    });
})();

// Web UI用 config.js 出力
app.get('/config.js', (req, res) => {
    const wsUrl = process.env.WS_SERVER_URL || `ws://localhost:${WS_PORT}`;
    res.setHeader('Content-Type', 'application/javascript');
    res.send(`window.WS_SERVER_URL = "${wsUrl}";`);
});