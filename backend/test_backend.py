import os
import sys
import unittest
import tempfile
import shutil
import json
from pathlib import Path

# Add app to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.auth import hash_password, verify_password, validate_password_strength
from app.encrypt import encrypt_field, decrypt_field, is_encrypted, encrypt_dict, decrypt_dict
from app import secrets
from app.notify import _render_email

class TestAuthFunctions(unittest.TestCase):
    def test_password_hashing(self):
        password = "SecurePassword123!"
        hashed = hash_password(password)
        self.assertNotEqual(password, hashed)
        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("wrong_password", hashed))

    def test_password_strength_validation(self):
        # Too short
        self.assertIn("at least 12 characters", validate_password_strength("Short1!"))
        # Missing uppercase
        self.assertIn("one uppercase letter", validate_password_strength("lowercase123!"))
        # Missing lowercase
        self.assertIn("one lowercase letter", validate_password_strength("UPPERCASE123!"))
        # Missing number
        self.assertIn("digit", validate_password_strength("NoNumbersHere!"))
        # Valid password
        self.assertIsNone(validate_password_strength("ValidP@ssword123"))


class TestEncryptFunctions(unittest.TestCase):
    def test_field_encryption(self):
        plaintext = "sensitive data to encrypt"
        encrypted = encrypt_field(plaintext)
        
        self.assertTrue(is_encrypted(encrypted))
        self.assertTrue(encrypted.startswith("enc:"))
        
        decrypted = decrypt_field(encrypted)
        self.assertEqual(plaintext, decrypted)
        
        # Test empty input
        self.assertEqual("", encrypt_field(""))
        self.assertEqual("", decrypt_field(""))
        
        # Test non-encrypted fallback
        self.assertEqual("not_encrypted", decrypt_field("not_encrypted"))

    def test_dict_encryption(self):
        data = {
            "username": "user1",
            "email": "user1@example.com",
            "ssn": "123-456-7890",
            "age": 30
        }
        fields_to_encrypt = ["email", "ssn"]
        
        encrypted_data = encrypt_dict(data, fields_to_encrypt)
        self.assertEqual(data["username"], encrypted_data["username"])
        self.assertEqual(data["age"], encrypted_data["age"])
        self.assertTrue(is_encrypted(encrypted_data["email"]))
        self.assertTrue(is_encrypted(encrypted_data["ssn"]))
        
        decrypted_data = decrypt_dict(encrypted_data, fields_to_encrypt)
        self.assertEqual(data, decrypted_data)


class TestSecretsFunctions(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for the secrets vault
        self.temp_dir = tempfile.mkdtemp()
        self.old_vault_root = secrets.VAULT_ROOT
        self.old_install_id_path = secrets.INSTALL_ID_PATH
        self.old_manifest_path = secrets.MANIFEST_PATH
        self.old_main_env_path = secrets.MAIN_ENV_PATH
        
        secrets.VAULT_ROOT = Path(self.temp_dir)
        secrets.INSTALL_ID_PATH = secrets.VAULT_ROOT / "install.id"
        secrets.MANIFEST_PATH   = secrets.VAULT_ROOT / "secrets.json"
        secrets.MAIN_ENV_PATH   = secrets.VAULT_ROOT / "env" / "main.env"

    def tearDown(self):
        # Clean up temp directory
        shutil.rmtree(self.temp_dir)
        secrets.VAULT_ROOT = self.old_vault_root
        secrets.INSTALL_ID_PATH = self.old_install_id_path
        secrets.MANIFEST_PATH = self.old_manifest_path
        secrets.MAIN_ENV_PATH = self.old_main_env_path

    def test_vault_is_mounted(self):
        # Not mounted yet (missing install.id)
        self.assertFalse(secrets.vault_is_mounted())
        
        # Mount it
        secrets.INSTALL_ID_PATH.write_text("test-uuid-12345")
        self.assertTrue(secrets.vault_is_mounted())

    def test_get_install_uuid(self):
        self.assertIsNone(secrets.get_install_uuid())
        secrets.INSTALL_ID_PATH.write_text("my-install-uuid")
        self.assertEqual("my-install-uuid", secrets.get_install_uuid())

    def test_get_manifest(self):
        self.assertIsNone(secrets.get_manifest())
        
        manifest_data = {
            "version": "1.0",
            "files": [
                {"path": "env/main.env", "type": "env"},
                {"path": "config/pdns.conf", "type": "config"}
            ],
            "services": {
                "webpanel": {
                    "secrets": ["env/main.env"]
                }
            }
        }
        secrets.MANIFEST_PATH.write_text(json.dumps(manifest_data))
        self.assertEqual(manifest_data, secrets.get_manifest())

    def test_read_env_var(self):
        # Create env dir and file
        env_dir = secrets.VAULT_ROOT / "env"
        env_dir.mkdir(exist_ok=True)
        env_file = env_dir / "main.env"
        
        env_content = """
        # Master environment file
        SECRET_KEY=my_secret_key_123
        PORT=8000
        DEBUG=true
        """
        env_file.write_text(env_content)
        
        self.assertEqual("my_secret_key_123", secrets.read_env_var("SECRET_KEY"))
        self.assertEqual("8000", secrets.read_env_var("PORT"))
        self.assertEqual("true", secrets.read_env_var("DEBUG"))
        self.assertIsNone(secrets.read_env_var("NOT_EXIST"))

    def test_resolve_secret_path(self):
        secrets.INSTALL_ID_PATH.write_text("uuid")
        
        # Test non-existent path
        self.assertIsNone(secrets.resolve_secret_path("config/non-existent.conf"))
        
        # Test existent path
        config_dir = secrets.VAULT_ROOT / "config"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "pdns.conf"
        config_file.write_text("pdns-config")
        
        resolved = secrets.resolve_secret_path("config/pdns.conf")
        self.assertIsNotNone(resolved)
        self.assertEqual("pdns-config", resolved.read_text())


class TestNotificationFunctions(unittest.TestCase):
    def test_render_email(self):
        title = "Domain Status Alert"
        message = "Your domain has been updated successfully."
        details = {
            "Domain": "example.com",
            "Status": "Active",
            "IP Address": "192.168.1.1"
        }
        ts = "2026-06-11 10:46 UTC"
        
        html = _render_email(title, message, details, ts)
        self.assertIn(title, html)
        self.assertIn(message, html)
        self.assertIn("example.com", html)
        self.assertIn("Active", html)
        self.assertIn("192.168.1.1", html)
        self.assertIn(ts, html)


if __name__ == "__main__":
    unittest.main()
