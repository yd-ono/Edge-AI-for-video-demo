from confluent_kafka import Producer
import json
import time
import math
import random
import threading
import os

# Kafka 設定
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "data-mesh")

# Kafka Producer 設定
producer_config = {
    "bootstrap.servers": KAFKA_BROKER,
    "client.id": "python-producer",
    "acks": "all",
    "security.protocol": "PLAINTEXT",
}

# Kafka Producer インスタンス作成
producer = Producer(producer_config)

# 地球の半径 (メートル)
EARTH_RADIUS = 6371000

# 地理座標系は面倒なので、緯度経度座標系で計算する。
# 偵察部隊 (recces) の初期データ (連隊IDと兵科記号を追加)
recces_units = [
    {"id": "regimentA_recces1", "type": "recces", "latitude": 33.309514, "longitude": 131.252289},
    {"id": "regimentA_recces2", "type": "recces", "latitude": 33.310016, "longitude": 131.271601},
    {"id": "regimentB_recces1", "type": "recces", "latitude": 33.312813, "longitude": 131.321125},
]

# 敵 (enemy) の初期データ
enemy_units = [
    {"id": "enemy1", "latitude": 33.318116, "longitude": 131.249235}, 
    {"id": "enemy2", "latitude": 33.315000, "longitude": 131.260000},
    {"id": "enemy3", "latitude": 33.316500, "longitude": 131.270000},
    {"id": "enemy4", "latitude": 33.317000, "longitude": 131.280000},
    {"id": "enemy5", "latitude": 33.317500, "longitude": 131.290000},
    {"id": "enemy6", "latitude": 33.318000, "longitude": 131.300000},
    {"id": "enemy7", "latitude": 33.318000, "longitude": 131.300000},
    {"id": "enemy8", "latitude": 33.319116, "longitude": 131.260000},
    {"id": "enemy9", "latitude": 33.319116, "longitude": 131.270000},
]


# 度をラジアンに変換
def to_radians(degrees):
    return (degrees * math.pi) / 180

# ラジアンを度に変換
def to_degrees(radians):
    return (radians * 180) / math.pi

# 方位角 (bearing) を計算
def calculate_bearing(start, end):
    lat1, lon1 = map(to_radians, start)
    lat2, lon2 = map(to_radians, end)
    d_lon = lon2 - lon1

    x = math.sin(d_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)

    return (to_degrees(math.atan2(x, y)) + 360) % 360

# 2地点間の地球の球面状の距離をHaversineで出す
# 用途考えたら、Vincentyの方が精度良いけど反復計算なので、計算コスト考えてHaversineで。
def calculate_distance(start, end):
    lat1, lon1 = map(to_radians, start)
    lat2, lon2 = map(to_radians, end)

    d_lat = lat2 - lat1
    d_lon = lon2 - lon1

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    )
    return EARTH_RADIUS * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# 移動距離の座標を逆Haversineで出す
def calculate_next_point(lat, lon, distance, bearing):
    angular_distance = distance / EARTH_RADIUS
    bearing_rad = to_radians(bearing)

    lat1 = to_radians(lat)
    lon1 = to_radians(lon)

    new_lat = math.asin(
        math.sin(lat1) * math.cos(angular_distance) +
        math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing_rad)
    )
    new_lon = lon1 + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(new_lat),
    )

    return to_degrees(new_lat), to_degrees(new_lon)

# Xmごとにポイントを生成
def generate_positions(route, step=100):
    positions = []
    for i in range(len(route) - 1):
        start = route[i]
        end = route[i + 1]
        current = start
        bearing = calculate_bearing(start, end)

        while calculate_distance(current, end) > step:
            positions.append(current)
            current = calculate_next_point(current[0], current[1], step, bearing)

        positions.append(end)  # 最後のポイントを追加

    return positions

# メッセージをKafkaに送信する関数
def send_to_kafka(message):
    json_message = json.dumps(message)
    producer.produce(KAFKA_TOPIC, key=str(message["id"]), value=json.dumps(message).encode("utf-8"))
    producer.flush()
    print(f"Sent: {json_message}")

##後できれいにする。
## A連隊配置　(大隊単位で作ればよかったねぇ。。)
# regimentA_recces1 の近くに tank を配置
tank_lat, tank_lon = calculate_next_point(33.309514, 131.252289, 50, random.uniform(0, 360))
recces_units.append({"id": "regimentA_tank1", "type": "tank", "latitude": tank_lat, "longitude": tank_lon})

# tank の後方 10m に infantry を配置
infantry_lat, infantry_lon = calculate_next_point(tank_lat, tank_lon, 150, 180)  # 180度方向（後方）
recces_units.append({"id": "regimentA_infantry1", "type": "infantry", "latitude": infantry_lat, "longitude": infantry_lon})


# regimentA_recces1 の近くに tank を配置
tank_lat, tank_lon = calculate_next_point(33.310016, 131.271601, 150, random.uniform(0, 360))
recces_units.append({"id": "regimentA_tank2", "type": "tank", "latitude": tank_lat, "longitude": tank_lon})

# regimentA_recces1 の近くに infantry を2つ配置
infantry_lat, infantry_lon = calculate_next_point(33.310016, 131.271601, 150, random.uniform(0, 180))
recces_units.append({"id": "regimentA_infantry2", "type": "infantry", "latitude": infantry_lat, "longitude": infantry_lon})


## B連隊配置
# regimentB_recces1 の近くに tank を配置
tank_lat_B, tank_lon_B = calculate_next_point(33.312813, 131.321125, 100, random.uniform(0, 360))
recces_units.append({"id": "regimentB_tank1", "type": "tank", "latitude": tank_lat_B, "longitude": tank_lon_B})

# tank の後方に infantry を1つ配置
infantry_lat_B, infantry_lon_B = calculate_next_point(tank_lat_B, tank_lon_B, 50, 180)  # 180度方向（後方）
recces_units.append({"id": "regimentB_infantry1", "type": "infantry", "latitude": infantry_lat_B, "longitude": infantry_lon_B})

# tank の後方に infantry を1つ配置
# infantry_lat_B, infantry_lon_B = calculate_next_point(infantry_lat_B, infantry_lon_B, 25, 270)
# recces_units.append({"id": "regimentB_infantry2", "type": "infantry", "latitude": infantry_lat, "longitude": infantry_lon})


# 連隊のランダム移動 (連隊ごとに移動方向を変更)
def move_recces_units():
    sequence_number = 0

    while True:
        for unit in recces_units:
            # tank は前方にゆっくり移動 (30m/s)
            # if "tank" in unit["type"]:
            #     movement_distance = 30
            #     movement_bearing = random.uniform(0, 90)  # 北方向
            # # infantry は tank を追従 (25m/s)
            # elif "infantry" in unit["type"]:
            #     movement_distance = 25
            #     movement_bearing = random.uniform(0, 90)  # 北方向
            # # recce は 10m ランダム移動
            # else:
            #     movement_distance = 10
            #     movement_bearing = random.uniform(0, 360)  # ランダム

            # 連隊ごとに移動方向を変更
            if "regimentA" in unit["id"]:
                random_bearing = random.uniform(0, 90)  # 北向き
            elif "regimentB" in unit["id"]:
                random_bearing = random.uniform(225, 315)  # 北西向き
            else:
                random_bearing = random.uniform(0, 360)  # その他


            # 10m 移動
            new_lat, new_lon = calculate_next_point(unit["latitude"], unit["longitude"], 10, random_bearing)

            # 座標を更新
            unit["latitude"], unit["longitude"] = new_lat, new_lon

            # Kafka に送信
            message = {
                "id": unit["id"],
                "sequence_number": sequence_number,
                "type": unit["type"],
                "latitude": new_lat,
                "longitude": new_lon,
                "timestamp": int(time.time() * 1000),  # ミリ秒単位で送信 time.timeは秒単位だった
            }
            send_to_kafka(message)
            sequence_number += 1

        time.sleep(1)  # 1秒ごとに移動


# 敵 (enemy) の移動データを定期的に送信
def move_enemy_units():
    while True:
        for enemy in enemy_units:
            if enemy["id"] in ["enemy8", "enemy9"]:
                # enemy8, enemy9 は北 (0°) に移動
                new_lat, new_lon = calculate_next_point(enemy["latitude"], enemy["longitude"], 40, 0)  # 0° = 真北
            else:
                # その他の敵はランダム (0°〜180°) に移動
                random_bearing = random.uniform(0, 180)
                new_lat, new_lon = calculate_next_point(enemy["latitude"], enemy["longitude"], 8, random_bearing)

            # 座標を更新
            enemy["latitude"], enemy["longitude"] = new_lat, new_lon

            # Kafka に送信
            message = {
                "id": enemy["id"],
                "type": "enemy",
                "latitude": new_lat,
                "longitude": new_lon,
                "timestamp": int(time.time() * 1000),  # ミリ秒単位で送信
            }
            send_to_kafka(message)

        time.sleep(1)  # 1秒ごとに移動

# マルチスレッドで `recces` と `enemy` を並行実行
if __name__ == "__main__":
    try:
        thread_recces = threading.Thread(target=move_recces_units, daemon=True)
        thread_enemy = threading.Thread(target=move_enemy_units, daemon=True)

        thread_recces.start()
        thread_enemy.start()

        # メインスレッドをブロックして終了しないようにする
        thread_recces.join()
        thread_enemy.join()

    except KeyboardInterrupt:
        print("\nProducer interrupted.")
    finally:
        print("Closing producer...")
        producer.flush()