# ssd1306_subregion_driver.py
# 整合版：SSD1306/SSD1315 I2C 驱动，支持子区域、硬件滚动、图片显示
# 继承 FrameBuffer，绘图坐标相对于子区域 (0,0)
# 测试流程涵盖填充、边框、文字、软件滚动和硬件滚动

from micropython import const
import framebuf
from machine import Pin, I2C
import time

# ---------- 寄存器定义 ----------
SET_CONTRAST        = const(0x81)
SET_ENTIRE_ON       = const(0xa4)
SET_NORM_INV        = const(0xa6)
SET_DISP            = const(0xae)
SET_MEM_ADDR        = const(0x20)
SET_COL_ADDR        = const(0x21)
SET_PAGE_ADDR       = const(0x22)
SET_DISP_START_LINE = const(0x40)
SET_SEG_REMAP       = const(0xa0)
SET_MUX_RATIO       = const(0xa8)
SET_COM_OUT_DIR     = const(0xc0)
SET_DISP_OFFSET     = const(0xd3)
SET_COM_PIN_CFG     = const(0xda)
SET_DISP_CLK_DIV    = const(0xd5)
SET_PRECHARGE       = const(0xd9)
SET_VCOM_DESEL      = const(0xdb)
SET_CHARGE_PUMP     = const(0x8d)

# 滚动命令
SCROLL_HORIZONTAL_RIGHT = const(0x26)
SCROLL_HORIZONTAL_LEFT  = const(0x27)
SCROLL_VERTICAL_AND_HORIZONTAL = const(0x29)
SCROLL_VERTICAL         = const(0x2A)
SCROLL_ACTIVATE         = const(0x2F)
SCROLL_DEACTIVATE       = const(0x2E)
SET_VERTICAL_SCROLL_AREA = const(0xA3)


class SSD1315_I2C(framebuf.FrameBuffer):
    """
    仅维护子区域缓冲区的 SSD1306/SSD1315 I2C 驱动，支持硬件滚动。
    物理尺寸与子区域分离，绘图坐标相对于子区域左上角 (0,0)。
    """

    def __init__(self, phys_width, phys_height, i2c, addr=0x3c,
                 x_offset=0, y_offset=0, sub_width=None, sub_height=None,
                 external_vcc=False):
        """
        参数：
            phys_width, phys_height : 物理屏幕分辨率（如 128,64）
            i2c                       : I2C 对象
            addr                      : I2C 地址（默认 0x3c）
            x_offset, y_offset        : 子区域左上角在物理屏幕上的坐标
            sub_width, sub_height     : 子区域尺寸（若为 None 则等于物理尺寸）
            external_vcc              : 是否使用外部 VCC（影响电荷泵设置）
        """
        self.phys_width = phys_width
        self.phys_height = phys_height
        self.x_offset = x_offset
        self.y_offset = y_offset
        if sub_width is None:
            sub_width = phys_width
        if sub_height is None:
            sub_height = phys_height
        self.sub_width = sub_width
        self.sub_height = sub_height
        # 计算页数（子区域高度按 8 像素对齐，一般取模工具保证）
        self.pages = sub_height // 8
        # 分配子区域缓冲区（MONO_VLSB 格式）
        self.buffer = bytearray(self.pages * sub_width)
        super().__init__(self.buffer, sub_width, sub_height, framebuf.MONO_VLSB)

        self.i2c = i2c
        self.addr = addr
        self.external_vcc = external_vcc
        self.temp = bytearray(2)

        self.init_display()

    def write_cmd(self, cmd):
        """发送单字节命令"""
        self.temp[0] = 0x80
        self.temp[1] = cmd
        self.i2c.writeto(self.addr, self.temp)

    def write_cmd_list(self, cmds):
        """发送多字节命令序列"""
        for c in cmds:
            self.write_cmd(c)

    def write_data(self, buf):
        """发送数据（带控制字节 0x40）"""
        self.i2c.writeto(self.addr, b'\x40' + buf)

    def init_display(self):
        """初始化显示屏，设置为水平寻址模式"""
        cmds = [
            SET_DISP | 0x00,           # 关闭显示
            SET_MEM_ADDR, 0x00,        # 水平寻址模式
            SET_DISP_START_LINE | 0x00,
            SET_SEG_REMAP | 0x01,      # 段映射（列127 → SEG0）
            SET_MUX_RATIO, self.phys_height - 1,
            SET_COM_OUT_DIR | 0x08,    # 行扫描方向（COM[N] → COM0）
            SET_DISP_OFFSET, 0x00,
            SET_COM_PIN_CFG, 0x02 if self.phys_height == 32 else 0x12,
            SET_DISP_CLK_DIV, 0x80,
            SET_PRECHARGE, 0x22 if self.external_vcc else 0xf1,
            SET_VCOM_DESEL, 0x30,
            SET_CONTRAST, 0xff,
            SET_ENTIRE_ON,             # 全亮关闭
            SET_NORM_INV,              # 正常显示
            SET_CHARGE_PUMP, 0x10 if self.external_vcc else 0x14,
            SET_DISP | 0x01,           # 开启显示
        ]
        self.write_cmd_list(cmds)
        self.fill(0)
        self.show()

    def poweroff(self):
        self.write_cmd(SET_DISP | 0x00)

    def poweron(self):
        self.write_cmd(SET_DISP | 0x01)

    def contrast(self, contrast):
        self.write_cmd(SET_CONTRAST)
        self.write_cmd(contrast)

    def invert(self, invert):
        self.write_cmd(SET_NORM_INV | (invert & 1))

    def show(self):
        """将子区域 buffer 刷新到物理屏幕的指定偏移位置"""
        col_start = self.x_offset
        col_end   = self.x_offset + self.sub_width - 1
        page_start = self.y_offset // 8
        page_end   = (self.y_offset + self.sub_height - 1) // 8
        self.write_cmd(SET_COL_ADDR)
        self.write_cmd(col_start)
        self.write_cmd(col_end)
        self.write_cmd(SET_PAGE_ADDR)
        self.write_cmd(page_start)
        self.write_cmd(page_end)
        self.write_data(self.buffer)

    # ---------- 硬件滚动方法 ----------
    def scroll_horizontal(self, direction='left', start_page=0, end_page=None,
                          speed=0):
        """
        水平滚动（连续）。
        direction: 'left' 或 'right'
        start_page, end_page: 滚动影响的页范围（0~7）
        speed: 0~7，0最快，7最慢
        """
        if end_page is None:
            end_page = self.phys_height // 8 - 1
        self.write_cmd(SCROLL_DEACTIVATE)
        cmd = SCROLL_HORIZONTAL_RIGHT if direction == 'right' else SCROLL_HORIZONTAL_LEFT
        self.write_cmd_list([
            cmd, 0x00, start_page, speed, end_page,
            0x00, 0xFF  # 固定
        ])
        self.write_cmd(SCROLL_ACTIVATE)

    def scroll_vertical(self, direction='down', start_page=0, end_page=None,
                        vertical_offset=0, speed=0):
        """
        垂直滚动。
        direction: 'up' 或 'down'（实际由 vertical_offset 正负决定）
        start_page, end_page: 滚动影响的页范围
        vertical_offset: 偏移行数（0~63），正数向下，负数向上（内部处理取补码）
        speed: 0~7
        """
        if end_page is None:
            end_page = self.phys_height // 8 - 1
        self.write_cmd(SCROLL_DEACTIVATE)
        # 设置垂直滚动区域
        self.write_cmd(SET_VERTICAL_SCROLL_AREA)
        self.write_cmd(0)                      # 起始行
        self.write_cmd(self.phys_height)      # 总行数
        # 垂直偏移取低6位，若为负则取其补码表示
        offset = vertical_offset & 0x3F
        self.write_cmd_list([
            SCROLL_VERTICAL, 0x00, start_page, speed, end_page,
            offset
        ])
        self.write_cmd(SCROLL_ACTIVATE)

    def scroll_vertical_and_horizontal(self, direction='right', start_page=0,
                                       end_page=None, vertical_offset=0, speed=0):
        """
        垂直+水平混合滚动（对角线）。
        direction: 水平方向 'right' 或 'left'
        其他参数同上。
        """
        if end_page is None:
            end_page = self.phys_height // 8 - 1
        self.write_cmd(SCROLL_DEACTIVATE)
        self.write_cmd(SET_VERTICAL_SCROLL_AREA)
        self.write_cmd(0)
        self.write_cmd(self.phys_height)
        self.write_cmd_list([
            SCROLL_VERTICAL_AND_HORIZONTAL, 0x00, start_page, speed, end_page,
            vertical_offset & 0x3F,
            0x00, 0x00   # 固定
        ])
        self.write_cmd(SCROLL_ACTIVATE)

    def stop_scroll(self):
        """停止所有滚动"""
        self.write_cmd(SCROLL_DEACTIVATE)

    # ---------- 高性能图片/汉字显示 ----------
    def newBuffer(self, data, w, h, x=0, y=0, format=framebuf.MONO_VLSB):
        """
        直接使用预编码的字节数据显示图片/汉字（最高效）。
        data : bytes/bytearray，已按指定格式打包。
        w, h : 像素宽度和高度。
        x, y : 在子区域内的绘制坐标。
        format: 默认为 MONO_VLSB（纵向取模低位在前）。
        """
        fbuf = framebuf.FrameBuffer(data, w, h, format)
        self.blit(fbuf, x, y)

    def set_rotation(self, rotation):
        """
        设置屏幕旋转/镜像。
        rotation: 0 - 正常, 1 - 水平翻转(左右镜像), 2 - 垂直翻转(上下镜像), 3 - 180度翻转
        """
        seg_remap = 0x00 if rotation in (0, 2) else 0x01  # bit0: 0正常,1重映射
        com_dir = 0x00 if rotation in (0, 1) else 0x08   # bit3: 0正常,1反向
        self.write_cmd(SET_SEG_REMAP | seg_remap)
        self.write_cmd(SET_COM_OUT_DIR | com_dir)


# ========== 测试流程（基于 ssd1306_direct_write.py） ==========
print("SSD1306 子区域驱动测试")

# ---------- I2C 初始化 ----------
i2c = I2C(0, scl=Pin(6), sda=Pin(5), freq=400000)
addr = 0x3c
if 0x3d in i2c.scan():
    addr = 0x3d
print("I2C addr:", hex(addr))

# ---------- 创建显示对象（子区域 72x40，偏移 28,24） ----------
display = SSD1315_I2C(
    phys_width=128,
    phys_height=64,
    i2c=i2c,
    addr=addr,
    x_offset=28,
    y_offset=24,
    sub_width=72,
    sub_height=40,
    external_vcc=False
)

# 注意：display 本身就是 FrameBuffer，可以直接调用 fill, rect, text 等
W, H = display.sub_width, display.sub_height

# ---------- 测试 1：填充白色 ----------
print("Test 1: Fill area white")
display.fill(1)
display.show()
time.sleep(1)

# ---------- 测试 2：清除 ----------
print("Test 2: Clear area")
display.fill(0)
display.show()
time.sleep(1)

# ---------- 测试 3：边框和文字 ----------
print("Test 3: Draw border and text")
display.fill(0)
display.rect(0, 0, W, H, 1)          # 边框
display.text("OLED", 10, 12, 1)
display.text("Test",  20, 24, 1)
display.show()
time.sleep(2)

# ---------- 测试 4：软件滚动文字（模拟移动） ----------
print("Test 4: Software scrolling text")
text = "Hello"
tw = len(text) * 8
for offset in range(0, W - tw + 1, 2):
    display.fill(0)
    display.rect(0, 0, W, H, 1)
    display.text(text, offset, 16, 1)
    display.show()
    time.sleep_ms(50)

# ---------- 测试 5：硬件滚动（水平） ----------
print("Test 5: Hardware horizontal scroll (right) for 3 seconds")
display.fill(0)
display.text("Scroll", 10, 12, 1)
display.text("Demo", 20, 24, 1)
display.show()
time.sleep(0.5)
# 启动水平滚动（影响所有页，速度适中）
display.scroll_horizontal(direction='right', start_page=0, end_page=7, speed=4)
time.sleep(3)
display.stop_scroll()

print("Test 6: Hardware vertical scroll for 3 seconds")
display.fill(0)
display.text("Vertical", 10, 12, 1)
display.text("Demo", 20, 24, 1)
display.show()
time.sleep(0.5)
# 垂直滚动：向下偏移 16 行，影响所有页
display.scroll_vertical(direction='down', start_page=0, end_page=7, vertical_offset=16, speed=2)
time.sleep(3)
display.stop_scroll()

print("All tests done.")
