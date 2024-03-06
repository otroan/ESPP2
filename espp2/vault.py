import json
import os

class VaultException(Exception):
    pass
class Vault:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Vault, cls).__new__(cls)
            cls._instance._data = {}
            # Read vault path from environment variable
            vault_path = os.environ.get('ESPP2_VAULT_PATH')
            if not vault_path:
                raise VaultException('ESPP2_VAULT_PATH environment variable not set')
            with open(vault_path, 'r', encoding='utf-8') as fp:
                cls._instance._data = json.load(fp)
        if not cls._instance._data:
            raise VaultException('Vault is empty')
        return cls._instance

    def __getitem__(self, key):
        return self._data.get(key)
