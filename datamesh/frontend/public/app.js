///////////////////////
// Mapの設定
///////////////////////

// 初期マップ設定
const map = L.map('map').setView([33.308143, 131.285897], 14);
const WS_SERVER_URL = window.WS_SERVER_URL || "ws://localhost:8081";

// OpenStreetMap タイルレイヤー
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
}).addTo(map);

// マーカー管理
const markers = {};
const circles = {};
const circleMarkers = {};  // 赤い丸（circleMarker）用のオブジェクト


// ===== 要請UI =====

// PiDogの状態を表示
const statusLabel = document.createElement('div');
statusLabel.id = 'pidog-status';
statusLabel.style.position = 'absolute';
statusLabel.style.top = '10px';
statusLabel.style.left = '50%';
statusLabel.style.transform = 'translateX(-50%)';
statusLabel.style.backgroundColor = '#e0e0e0';
statusLabel.style.border = '1px solid #888';
statusLabel.style.borderRadius = '6px';
statusLabel.style.padding = '8px 16px';
statusLabel.style.fontSize = '16px';
statusLabel.style.fontWeight = 'bold';
statusLabel.style.zIndex = '1000';
statusLabel.innerText = 'PiDogオート';
document.body.appendChild(statusLabel);

// 不審物アラート
const alertBox = document.createElement('div');
alertBox.id = 'alert-box';
alertBox.style.position = 'absolute';
alertBox.style.top = '70px';
alertBox.style.right = '10px';
alertBox.style.backgroundColor = '#ffcccc';
alertBox.style.color = '#990000';
alertBox.style.padding = '10px';
alertBox.style.border = '2px solid red';
alertBox.style.borderRadius = '6px';
alertBox.style.fontWeight = 'bold';
alertBox.style.zIndex = '1000';
alertBox.style.display = 'none';
alertBox.innerText = '⚠️ 不審物検出!PiDogを出動するか判断してください';
document.body.appendChild(alertBox);

// 要請内容入力フォーム
const requestInput = document.createElement('input');
requestInput.type = 'text';
requestInput.placeholder = '例: forward';
requestInput.style.position = 'absolute';
requestInput.style.bottom = '100px';
requestInput.style.left = '10px';
requestInput.style.padding = '8px';
requestInput.style.zIndex = '1000';
requestInput.value = 'forward';
document.body.appendChild(requestInput);

// ボタンコンテナ（Flex配置）
const requestControls = document.createElement('div');
requestControls.style.position = 'absolute';
requestControls.style.bottom = '50px';
requestControls.style.left = '10px';
requestControls.style.display = 'flex';
requestControls.style.gap = '10px';
requestControls.style.zIndex = '1000';
document.body.appendChild(requestControls);

// 要請ボタン
const requestButton = document.createElement('button');
requestButton.innerText = '要請';
requestButton.style.padding = '10px 16px';
requestButton.style.backgroundColor = 'lightgreen';
requestButton.style.border = '1px solid black';
requestButton.style.cursor = 'pointer';
requestButton.onclick = () => {
    const action = requestInput.value || 'forward';
    socket.send(JSON.stringify({ topic: 'pidog', action }));
    statusLabel.innerText = 'PiDog出動中';
    requestButton.style.backgroundColor = '#00cc66';  // 押した感
};
requestControls.appendChild(requestButton);

// 要請解除ボタン
const cancelButton = document.createElement('button');
cancelButton.innerText = '要請解除';
cancelButton.style.padding = '10px 16px';
cancelButton.style.backgroundColor = '#f5f5f5';
cancelButton.style.border = '1px solid black';
cancelButton.style.cursor = 'pointer';
cancelButton.onclick = () => {
    socket.send(JSON.stringify({ topic: 'pidog', action: 'auto' }));
    statusLabel.innerText = 'PiDogオート';
    requestButton.style.backgroundColor = 'lightgreen';  // 元に戻す
};
requestControls.appendChild(cancelButton);



///////////////////////
// イベント処理
///////////////////////

// マウス移動時に座標を表示
map.on('mousemove', (event) => {
    const { lat, lng } = event.latlng;
    const coordinatesDiv = document.getElementById('coordinates');
    coordinatesDiv.textContent = `Mouse Location: Latitude ${lat.toFixed(6)}, Longitude ${lng.toFixed(6)}`;
});

// マーカーとサークルを削除する関数
function clearMap() {
    // すべてのマーカーを削除
    Object.values(markers).forEach(marker => marker.remove());
    Object.values(circles).forEach(circle => circle.remove());

    // **すべての circleMarker を削除**
    Object.values(circleMarkers).forEach(markerList => {
        markerList.forEach(circleMarker => circleMarker.remove()); // 過去の `circleMarker` も削除
    });

    // オブジェクトを空にする
    Object.keys(markers).forEach(key => delete markers[key]);
    Object.keys(circles).forEach(key => delete circles[key]);
    Object.keys(circleMarkers).forEach(key => delete circleMarkers[key]); // `circleMarker` も削除

    console.log('All markers, circles, and circleMarkers have been cleared.');
}


// HTMLボタンに削除機能を追加（左下に配置）
const clearButton = document.createElement('button');
clearButton.textContent = 'マーカー削除';
clearButton.style.position = 'absolute';
clearButton.style.bottom = '10px';
clearButton.style.left = '10px';
clearButton.style.zIndex = '1000';
clearButton.style.padding = '10px';
clearButton.style.backgroundColor = 'white';
clearButton.style.border = '1px solid black';
clearButton.style.cursor = 'pointer';
clearButton.onclick = clearMap;
document.body.appendChild(clearButton);

///////////////////////
// WebSocket
///////////////////////

// WebSocket接続
const socket = new WebSocket(WS_SERVER_URL);

socket.onopen = () => {
    console.log('WebSocket connection established');
};

socket.onerror = (error) => {
    console.error('WebSocket error:', error);
};

let alertVisible = false;  // アラート表示状態を記録

// Kafkaから受信したデータを処理
socket.onmessage = (event) => {
    
    try {
        const location = JSON.parse(event.data);
        // console.log('Received from WebSocket:', location);

        // アイコンの種類を選択
        let iconUrl;
        if (location.type === 'enemy') {
            iconUrl = 'images/symbol_enemy.png';
        } else if (location.type === 'tank') {
            iconUrl = 'images/symbol_tank.png';
        } else if (location.type === 'infantry') {
            iconUrl = 'images/symbol_infantry.png';
        } else {
            iconUrl = 'images/symbol_recces.png'; // デフォルトのアイコン
        }

        // `tank`, `infantry` の処理（マーカーの更新・追加）
        if (location.type === 'tank' || location.type === 'infantry') {
            if (markers[location.id]) {
                // 既存マーカーを更新
                markers[location.id].setLatLng([location.latitude, location.longitude]);
                markers[location.id].setPopupContent(
                    `Type: ${location.type}<br>ID: ${location.id}<br>Timestamp: ${new Date(location.timestamp).toLocaleString()}`
                );
            } else {
                // 新規マーカーを作成
                const newMarker = L.marker([location.latitude, location.longitude], {
                    icon: L.icon({ iconUrl, iconSize: [32, 32], iconAnchor: [16, 16] }),
                }).addTo(map).bindPopup(
                    `Type: ${location.type}<br>ID: ${location.id}<br>Timestamp: ${new Date(location.timestamp).toLocaleString()}`
                );
                markers[location.id] = newMarker;
            }
        }

       // `recces`データの処理
       if (location.type === 'recces') {
        if (markers[location.id]) {
            // 既存マーカーとCircleを更新
            const marker = markers[location.id];
            marker.setLatLng([location.latitude, location.longitude]);
            marker.setPopupContent(
                `Type: ${location.type}<br>ID: ${location.id}<br>Timestamp: ${new Date(location.timestamp).toLocaleString()}`
            );

            const circle = circles[location.id];
            circle.setLatLng([location.latitude, location.longitude]);
        } else {
            // 新規マーカーとCircleを作成
            const newMarker = L.marker([location.latitude, location.longitude], {
                icon: L.icon({
                    iconUrl: iconUrl,
                    iconSize: [32, 32],
                    iconAnchor: [16, 16],
                }),
            });
            newMarker.addTo(map).bindPopup(
                `Type: ${location.type}<br>ID: ${location.id}<br>Timestamp: ${new Date(location.timestamp).toLocaleString()}`
            );
            markers[location.id] = newMarker;

            const newCircle = L.circle([location.latitude, location.longitude], {
                radius: 2000, // 半径2000m
                color: 'blue',
                fillColor: 'blue',
                fillOpacity: 0.2,
            });
            newCircle.addTo(map);
            circles[location.id] = newCircle;
        }
    }

    // 画面上にアラート表示
    // server.js が alert: true を送ってきた場合のみアラート表示
    try {
    
        if (location.alert === true && !alertVisible) {
          alertBox.style.display = 'block';
          alertVisible = true;
        }
    
        // alert: false の場合、確実に非表示にする
        if (location.alert === false && alertVisible) {
          alertBox.style.display = 'none';
          alertVisible = false;
        }
    
      } catch (e) {
        console.error('WebSocket message error:', e);
      }
  

    // `enemy` の処理
    if (location.type === 'enemy') {
        const isInsideAnyCircle = Object.values(circles).some((circle) => {
            const circleCenter = circle.getLatLng();
            const distance = map.distance(circleCenter, [location.latitude, location.longitude]);
            return distance <= circle.getRadius();
        });

        if (isInsideAnyCircle) {
            if (markers[location.id]) {
                // 既存マーカーの位置を取得
                const marker = markers[location.id];
                const prevLatLng = marker.getLatLng();

                // 以前の位置に赤い丸を追加
                const circleMarker = L.circleMarker(prevLatLng, {
                    radius: 3,
                    color: 'red',
                    fillColor: 'red',
                    fillOpacity: 0.3,
                }).addTo(map);

                // marker からポップアップ内容を取得し、circleMarker に適用
                const markerPopupContent = marker.getPopup().getContent();
                circleMarker.bindPopup(markerPopupContent);

                // 管理リストに追加
                // `circleMarkers` をリストとして管理し、すべての `circleMarker` を記録
                if (!circleMarkers[location.id]) {
                    circleMarkers[location.id] = [];
                }
                circleMarkers[location.id].push(circleMarker); // 過去のマーカーも記録
                
                // マーカーを更新
                marker.setLatLng([location.latitude, location.longitude]);
                marker.setPopupContent(
                    `Type: ${location.type}<br>ID: ${location.id}<br>Timestamp: ${new Date(location.timestamp).toLocaleString()}`
                );
            } else {
                // 新規マーカーを作成
                const newMarker = L.marker([location.latitude, location.longitude], {
                    icon: L.icon({
                        iconUrl: iconUrl,
                        iconSize: [32, 32],
                        iconAnchor: [16, 16],
                    }),
                }).addTo(map).bindPopup(
                    `Type: ${location.type}<br>ID: ${location.id}<br>Timestamp: ${new Date(location.timestamp).toLocaleString()}`
                );
                markers[location.id] = newMarker;
            }
        } else {
            // **範囲外の場合、最新の赤い丸をオレンジにする**
            if (circleMarkers[location.id] && circleMarkers[location.id].length > 0) {
                const lastCircleMarker = circleMarkers[location.id][circleMarkers[location.id].length - 1]; // **最新を取得**
                lastCircleMarker.setStyle({
                    color: 'orange',
                    fillColor: 'orange',
                    fillOpacity: 0.5,
                });
            }
            
            // マーカーを削除
            if (markers[location.id]) {
                markers[location.id].remove();
                delete markers[location.id];
                console.log(`Enemy ${location.id} is outside all recces circles. Last position marked in orange.`);
            }
        }
    }

    } catch (error) {
        console.error('Error parsing WebSocket message:', error);
    }
};