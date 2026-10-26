"""API contract tests; these do not open a webcam."""
import pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
try:
    from api import app
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
@unittest.skipUnless(FLASK_AVAILABLE, "Install Flask to run API contract tests")
class ApiContractTests(unittest.TestCase):
    def setUp(self): self.client = app.test_client()
    def test_health_is_explicit_about_model(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["model_trained"])
    def test_home_serves_dashboard(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"/api/analyze", r.data)
        r.close()
    def test_rejects_non_json(self):
        self.assertEqual(self.client.post("/api/analyze", data="nope", content_type="text/plain").status_code, 415)
    def test_rejects_missing_image(self):
        self.assertEqual(self.client.post("/api/analyze", json={}).status_code, 400)
    def test_rejects_invalid_base64(self):
        r = self.client.post("/api/analyze", json={"image":"data:image/jpeg;base64,%%%bad%%%"})
        self.assertEqual(r.status_code, 400)
if __name__ == "__main__": unittest.main()
