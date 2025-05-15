const express = require('express');
const WebSocket = require('ws');
const { Kafka, logLevel } = require('kafkajs');
const path = require('path');

const app = express();
const WS_PORT = process.env.WS_PORT || 8081;

const KAFKA_BROKERS = (process.env.KAFKA_BROKERS || 'localhost:9092').split(',');
console.log('[DEBUG] KAFKA_BROKERS from env =', process.env.KAFKA_BROKERS);
console.log('[DEBUG] KAFKA_BROKERS parsed =', KAFKA_BROKERS);

const TOPIC_DATA_MESH = process.env.TOPIC_DATA_MESH || 'data-mesh';

// Kafka設定
const kafka = new Kafka({ brokers: KAFKA_BROKERS, logLevel: logLevel.ERROR });
const producer = kafka.producer();
const consumer = kafka.consumer({ 
    groupId: 'data-mesh-regimentA',
    allowAutoTopicCreation: false,  // トピックの自動作成を無効化
    fetchMinBytes: 1,       // 最小取得バイト数
    fetchMaxBytes: 10485760, // 最大取得バイト数（10MB）
    maxBytesPerPartition: 1048576 // 1MB/Partition
});

// server.jsで実施する
// 静的ファイルのホスティング (index.html, app.js)
// app.use(express.static(path.join(__dirname, 'public')));

// HTTPサーバの起動
// const server = app.listen(PORT, () => {
//     console.log(`HTTP Server running at http://localhost:${PORT}`);
// });

// WebSocketサーバの起動
const wss = new WebSocket.Server({ port: WS_PORT });
console.log(`WebSocket Server running at ws://0.0.0.0:${WS_PORT}`);

wss.on('connection', (ws) => {
    console.log('WebSocket connected');

    // KafkaのConsumer
    (async () => {
        await consumer.connect();
        await consumer.subscribe({ topic: TOPIC_DATA_MESH, fromBeginning: false });

        await consumer.run({
            autoCommit: true, // 自動でオフセットをコミット
            heartbeatInterval: 3000, // 3秒ごとにハートビートを送信
            sessionTimeout: 30000,   // セッションタイムアウトを30秒に設定        
            eachMessage: async ({ message }) => {
                try {
                    if (!message.value) {
                        console.warn('Warning: Received empty Kafka message');
                        return;
                    }

                    const data = JSON.parse(message.value.toString('utf8'));

                    // **RegimentA のデータのみ送信**
                    if (data.id.startsWith("regimentA") || data.id.startsWith("enemy")) {
                        console.log('RegimentA: Received from Kafka:', data);
                        ws.send(JSON.stringify(data)); // WebSocket 経由でフロントに送信
                    }
                } catch (error) {
                    console.error('Error processing Kafka message:', error);
                }
            }
        });
    })();

    // KafkaのProducer(後でボタン押したら、Kafkaにデータを投げるとかで使う予定)
    ws.on('message', async (message) => {
        console.log('Received from Client:', message);
        //const data = JSON.parse(message);
        //await producer.send({ topic: 'data-mesh', messages: [{ value: JSON.stringify(data) }] });
        console.log('Sent to Kafka:', data);
    });

    ws.on('close', () => console.log('WebSocket disconnected'));
});

// Kafka Producer を起動
(async () => {
    await producer.connect();
    console.log('Kafka Producer Connected');
})();