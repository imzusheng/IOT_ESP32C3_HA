import gc

gc.enable()
gc.threshold(4096)

for _ in range(3):
    gc.collect()
