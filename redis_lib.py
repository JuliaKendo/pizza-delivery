import redis


class RedisDb(object):

    def __init__(self, host, port, password):
        self.redis_conn = redis.Redis(
            host=host,
            port=port,
            db=0, password=password
        )

    def clear_db(self):
        self.redis_conn.flushdb()

    def add_value(self, name, key, value):
        self.redis_conn.hset(name, mapping={key: value})

    def get_value(self, name, key):
        value = self.redis_conn.hmget(name, (key))[0]
        return value.decode("utf-8") if value else None
