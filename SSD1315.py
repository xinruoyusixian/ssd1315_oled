

# ssd1306_subregion.py
# 针对子区域优化的 SSD1306 I2C 驱动，支持硬件滚动和高效图片显示

from micropython import const
import framebuf

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
    仅维护子区域缓冲区的 SSD1306 I2C 驱动，支持硬件滚动。
    物理尺寸与子区域分离，绘图坐标相对于子区域左上角 (0,0)。
    """

    def __init__(self, phys_width, phys_height, i2c, addr=0x3c,x_offset=0, y_offset=0, sub_width=None, sub_height=None,external_vcc=False):
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
        # 参数格式：命令, 0x00, start_page, speed, end_page, vertical_offset, ...
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

    # （可选）兼容旧二维列表方式，但建议使用一维字节数组
    def newBuffer_from_2d(self, arr, x=0, y=0):
        """
        从二维字节数组（每行为字节列表）转换并显示。
        效率较低，仅用于兼容旧代码。
        """
        if not arr:
            return
        # 展平为一维 bytearray

        buf = bytearray()

        for row in arr:

            buf.extend(row)

        # 计算像素尺寸：每行字节数*8，行数*8

        w = len(arr[0]) * 8

        h = len(arr) * 8

        fbuf = framebuf.FrameBuffer(buf, w, h, framebuf.MONO_VLSB)
        self.blit(fbuf, x, y)
    def set_rotation(self, rotation):

        """

        设置屏幕旋转/镜像。

        rotation: 0 - 正常, 1 - 水平翻转(左右镜像), 2 - 垂直翻转(上下镜像), 3 - 180度翻转

        """

        seg_remap = 0x00 if rotation in (0, 2) else 0x01  # bit0: 0正常,1重映射
        com_dir = 0x00 if rotation in (0, 1) else 0x08   # bit3: 0正常,1反向
        self.write_cmd(SET_SEG_REMAP | seg_remap)   # SET_SEG_REMAP 命令低bit控制
        self.write_cmd(SET_COM_OUT_DIR | com_dir)   # SET_COM_OUT_DIR 命令的bit3控制
