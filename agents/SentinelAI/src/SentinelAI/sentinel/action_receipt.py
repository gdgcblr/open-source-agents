import hashlib, json
class ActionReceipt:
    def create(self, action, risk, allowed):
        payload={'action':action,'risk':risk,'allowed':allowed}
        payload['hash']=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        return payload
