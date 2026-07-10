# SSD1315_I2C.py
# 专为子区域优化的 SSD1306 I2C 驱动，节省内存

from micropython import const
import framebuf

# 寄存器定义（与官方一致）
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

class SSD1315_I2C(framebuf.FrameBuffer):
    """仅维护子区域缓冲区，I2C 驱动，支持指定偏移和尺寸"""

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
        # 计算页数（子区域高度按 8 像素对齐，通常为 8 的倍数）
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
        """发送命令字节"""
        self.temp[0] = 0x80
        self.temp[1] = cmd
        self.i2c.writeto(self.addr, self.temp)

    def write_data(self, buf):
        """发送数据（带控制字节）"""
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
        for c in cmds:
            self.write_cmd(c)
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
        
    def newBuffer(self, arr, x=0, y=0):
        """创建一个新buffer,用于显示汉字或者图片"""
        w = len(arr[0])
        h = len(arr) * w
        _buffer = bytearray(w * h)
        count = 0
        for lst in arr:
            for val in lst:
                _buffer[count] = val
                count += 1
        fbuf = framebuf.FrameBuffer(_buffer, w, h, framebuf.MONO_VLSB)
        del _buffer

        self.blit(fbuf, x, y)
    def show(self):
        """将子区域 buffer 刷新到物理屏幕的指定偏移位置"""
        # 计算列地址范围（物理列）
        col_start = self.x_offset
        col_end   = self.x_offset + self.sub_width - 1
        # 计算页地址范围（物理行映射到页）
        page_start = self.y_offset // 8
        page_end   = (self.y_offset + self.sub_height - 1) // 8
        # 设置列地址窗口
        self.write_cmd(SET_COL_ADDR)
        self.write_cmd(col_start)
        self.write_cmd(col_end)
        # 设置页地址窗口
        self.write_cmd(SET_PAGE_ADDR)
        self.write_cmd(page_start)
        self.write_cmd(page_end)
        # 发送子区域 buffer 数据
        self.write_data(self.buffer)
