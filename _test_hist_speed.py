"""临时测试：并行拉取历史日线的速度"""
import akshare as ak
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

codes = [
    '600000','000001','300750','601318','000858','600519','002594',
    '601012','000333','601888','600036','002475','601166','600900',
    '000568','002714','600276','601398','000661','002230',
    '600585','601857','000002','600887','601668','002415','600030',
    '601288','600809','000725','300059','002304','601899','600050',
    '000100','002142','601601','000063','002027','601006',
    '600104','002352','601390','300015','002460','601225','300122',
    '601818','002507','600309',
]

def fetch_one(code):
    t = time.time()
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, period='daily',
            start_date='20260305', end_date='20260312', adjust='qfq'
        )
        return code, len(df), time.time()-t, None
    except Exception as e:
        return code, 0, time.time()-t, str(e)

# 测试不同并发数
for workers in [5, 10, 20]:
    t0 = time.time()
    ok = 0
    fail = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_one, c): c for c in codes}
        for f in as_completed(futures):
            code, n, t, err = f.result()
            if n > 0:
                ok += 1
            else:
                fail += 1
    elapsed = time.time() - t0
    print(f"线程={workers:2d}: 成功={ok}, 失败={fail}, 耗时={elapsed:.1f}s")
    time.sleep(1)
