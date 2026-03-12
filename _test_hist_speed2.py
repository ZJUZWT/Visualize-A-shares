"""测试大规模并行拉取速度"""
import akshare as ak
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 先拿到全市场代码（用腾讯源生成）
codes = []
for i in range(600000, 606000):
    codes.append(str(i))
for i in range(688000, 690000):
    codes.append(str(i))
for i in range(1, 4000):
    codes.append(f"{i:06d}")
for i in range(300000, 302000):
    codes.append(str(i))

# 只取前 2000 只测试
test_codes = codes[:2000]
print(f"测试拉取 {len(test_codes)} 只股票...")

def fetch_one(code):
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, period='daily',
            start_date='20260305', end_date='20260312', adjust='qfq'
        )
        if df is not None and len(df) > 0:
            return code, len(df)
    except Exception:
        pass
    return code, 0

t0 = time.time()
ok = 0
fail = 0
total_rows = 0
WORKERS = 10
BATCH = 200

for batch_start in range(0, len(test_codes), BATCH):
    batch = test_codes[batch_start:batch_start+BATCH]
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(fetch_one, c): c for c in batch}
        for f in as_completed(futures):
            code, n = f.result()
            if n > 0:
                ok += 1
                total_rows += n
            else:
                fail += 1
    done = batch_start + len(batch)
    elapsed = time.time() - t0
    print(f"  进度: {done}/{len(test_codes)}, 成功={ok}, 失败={fail}, 耗时={elapsed:.1f}s")
    time.sleep(0.3)

elapsed = time.time() - t0
print(f"\n最终: 成功={ok}, 失败={fail}, 总行数={total_rows}, 耗时={elapsed:.1f}s")
print(f"速度: {ok/elapsed:.1f} 只/秒")
