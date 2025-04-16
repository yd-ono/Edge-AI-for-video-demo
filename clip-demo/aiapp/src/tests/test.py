from fastapi.testclient import TestClient
import numpy as np
from unittest.mock import patch, MagicMock
import unittest

import app 
client = TestClient(app.app)

class TestCLIPApp(unittest.TestCase):
    def test_get_labels(self):
        response = client.get("/get_labels")
        self.assertEqual(response.status_code, 200)
        self.assertIn("labels", response.json())

    def test_set_labels(self):
        response = client.post("/set_labels", json={"labels": "test1,test2,test3"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    @patch("app.cv2.VideoCapture")
    def test_camera_read(self, mock_capture):
        mock_instance = MagicMock()
        mock_instance.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_instance.isOpened.return_value = True
        mock_capture.return_value = mock_instance

        cam = app.Camera(0)
        frame = cam.read()
        self.assertIsInstance(frame, np.ndarray)

    def test_health(self):
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ovms_status", response.json())
        self.assertIn("mqtt_status", response.json())

if __name__ == "__main__":
    unittest.main()
