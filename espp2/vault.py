import json

class Vault:
    def __init__(self, file_path):
        self.file_path = file_path
        self._vault = {}
    
    def __getitem__(self, key):
        if key not in self._vault:
            self._vault.update(self._load_vault())
        return self._vault[key]

    def _load_vault(self):
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
