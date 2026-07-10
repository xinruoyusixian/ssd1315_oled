# test_subregion.py
from machine import Pin, I2C
import time
from ssd1315 import SSD1315_I2C

# 初始化 I2C
i2c = I2C(0, scl=Pin(6), sda=Pin(5), freq=400000)
print("I2C scan:", i2c.scan())

addr = 0x3c
if 0x3d in i2c.scan():
    addr = 0x3d
print("Using address:", hex(addr))

# 创建子区域驱动：物理 128x64，子区域从 (28,24) 开始，大小 72x40
oled = SSD1315_I2C(128, 64, i2c, addr,
                             x_offset=28, y_offset=24,
                             sub_width=72, sub_height=40)

# 测试 1: 填充白色
print("Fill white")
oled.fill(1)
oled.show()
time.sleep(1)

# 测试 2: 清屏
print("Clear")
oled.fill(0)
oled.show()
time.sleep(1)

# 测试 3: 绘制边框和文字
print("Draw border and text")
oled.fill(0)
oled.rect(0, 0, 72, 40, 1)         # 子区域边框
oled.text("OLED", 10, 12, 1)
oled.text("Test", 20, 24, 1)
oled.show()
time.sleep(2)

# 测试 4: 文字滚动
print("Scrolling text")
text = "Hello"
tw = len(text) * 8
for offset in range(0, 72 - tw + 1, 2):
    oled.fill(0)
    oled.rect(0, 0, 72, 40, 1)
    oled.text(text, offset, 16, 1)
    oled.show()
    time.sleep_ms(50)

print("Done.")
