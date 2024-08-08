# Edge-AI-for-video-demo

本リポジトリは、Yolov8をOpenVINOモデルサーバでデプロイし、リアルタイム物体検知アプリケーションのデモです。
動画はmjpegストリームとしてWebブラウザ上に表示します。

なお、Yolov8モデルをOpenVINO IRへの変換、およびFP32からInt8への量子化は以下のノートブックを使用して出力しています。

[OpenVINO形式のYolov8モデルの最適化](https://github.com/openvinotoolkit/openvino_notebooks/blob/2023.3/notebooks/230-yolov8-optimization/230-yolov8-object-detection.ipynb)

マニフェストディレクトリは[こちら](https://github.com/yd-ono/Edge-AI-for-video-demo-manifests)
