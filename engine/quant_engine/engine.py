"""QuantEngine — 量化引擎门面类（Task 4 完善）"""


class QuantEngine:
    def __init__(self, data_engine=None):
        self._data = data_engine
