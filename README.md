# Edge-AI-for-video-demo

Yolov8をOpenVINOモデルサーバでデプロイし、リアルタイム物体検知アプリケーションをデプロイします。
動画はmjpegストリームとしてWebブラウザ上に表示します。

なお、Yolov8モデルをOpenVINO IRへの変換、およびFP32からInt8への量子化は以下のノートブックを使用して出力しています。

[リアルタイム物体検知](https://docs.openvino.ai/2024/notebooks/yolov8-object-detection-with-output.html)

マニフェストディレクトリは[こちら](https://github.com/yd-ono/Edge-AI-for-video-demo-manifests)
