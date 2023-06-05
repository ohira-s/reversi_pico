#
# Waveshare 3.5inch Touch LCD display for Raspberry Pi PICO
# Graphic library class
#
from machine import Pin,SPI,PWM
import framebuf
import time
import os

LCD_DC   = 8
LCD_CS   = 9
LCD_SCK  = 10
LCD_MOSI = 11
LCD_MISO = 12
LCD_BL   = 13
LCD_RST  = 15
TP_CS    = 16
TP_IRQ   = 17


class TouchLCD_3inch5(framebuf.FrameBuffer):
    GET_TOUCH = 0             # Sence touch only
    GET_TOUCH_DOWN = 1        # Sence touch and detach, return a point touched
    GET_TOUCH_UP = 2          # Sence touch and detach, return a point detached

    def __init__(self, width=480, height=160):
        # Color definitions for RGB565 (R=5bit, G=6bit, B=5bit rrrr,rggg,gggb,bbbb)
                               # <--B-><--R--><--G->
        self.RED     = 0x07e0  # 0000 0111 1110 0000  OK
        self.BROWN   = 0x00a3  # 0000 0000 1010 0011  OK
        self.ORANGE  = 0x07e3  # 0000 0111 1110 0011  OK
        self.YELLOW  = 0x07ff  # 0000 0111 1111 1111  OK
        self.GREEN   = 0x001f  # 0000 0000 0001 1111  OK
        self.MINT    = 0x182f  # 0001 1000 0010 1111  OK
        self.SKYBLUE = 0xf81f  # 1111 1000 0001 1111  OK
        self.BLUE    = 0xf800  # 1111 1000 0000 0000  OK
        self.MAGENTA = 0xffe0  # 1111 1111 1110 0000  OK
        self.PINK    = 0xdffb  # 1101 1111 1111 1011  OK

        self.WHITE   = 0xffff  # 1111 1111 1111 1111  OK
        self.GREY    = 0x7bef  # 0111 1011 1110 1111  OK
        self.BLACK   = 0x0000  # 0000 0000 0000 0000  OK

        
        self.width = width
        self.height = height
        
        self.cs = Pin(LCD_CS,Pin.OUT)
        self.rst = Pin(LCD_RST,Pin.OUT)
        self.dc = Pin(LCD_DC,Pin.OUT)
        
        self.tp_cs =Pin(TP_CS,Pin.OUT)
        self.irq = Pin(TP_IRQ,Pin.IN)
        
        self.cs(1)
        self.dc(1)
        self.rst(1)
        self.tp_cs(1)
        self.spi = SPI(1,60_000_000,sck=Pin(LCD_SCK),mosi=Pin(LCD_MOSI),miso=Pin(LCD_MISO))
              
        self.buffer = bytearray(self.height * self.width * 2)
        super().__init__(self.buffer, self.width, self.height, framebuf.RGB565)
        self.init_display()

    def spi_freq(self, freq):
        self.spi = SPI(1,freq,sck=Pin(LCD_SCK),mosi=Pin(LCD_MOSI),miso=Pin(LCD_MISO))
        
    def write_cmd(self, cmd):
        self.cs(1)
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1)

    def write_data(self, buf):
        self.cs(1)
        self.dc(1)
        self.cs(0)
        #self.spi.write(bytearray([0X00]))
        self.spi.write(bytearray([buf]))
        self.cs(1)


    def init_display(self):
        """Initialize dispaly"""  
        self.rst(1)
        time.sleep_ms(5)
        self.rst(0)
        time.sleep_ms(10)
        self.rst(1)
        time.sleep_ms(5)
        self.write_cmd(0x21)
        self.write_cmd(0xC2)
        self.write_data(0x33)
        self.write_cmd(0XC5)
        self.write_data(0x00)
        self.write_data(0x1e)
        self.write_data(0x80)
        self.write_cmd(0xB1)
        self.write_data(0xB0)
        self.write_cmd(0x36)
        self.write_data(0x28)
        self.write_cmd(0XE0)
        self.write_data(0x00)
        self.write_data(0x13)
        self.write_data(0x18)
        self.write_data(0x04)
        self.write_data(0x0F)
        self.write_data(0x06)
        self.write_data(0x3a)
        self.write_data(0x56)
        self.write_data(0x4d)
        self.write_data(0x03)
        self.write_data(0x0a)
        self.write_data(0x06)
        self.write_data(0x30)
        self.write_data(0x3e)
        self.write_data(0x0f)
        self.write_cmd(0XE1)
        self.write_data(0x00)
        self.write_data(0x13)
        self.write_data(0x18)
        self.write_data(0x01)
        self.write_data(0x11)
        self.write_data(0x06)
        self.write_data(0x38)
        self.write_data(0x34)
        self.write_data(0x4d)
        self.write_data(0x06)
        self.write_data(0x0d)
        self.write_data(0x0b)
        self.write_data(0x31)
        self.write_data(0x37)
        self.write_data(0x0f)
        self.write_cmd(0X3A)
        self.write_data(0x55)
        self.write_cmd(0x11)
        time.sleep_ms(120)
        self.write_cmd(0x29)
        
        self.write_cmd(0xB6)
        self.write_data(0x00)
        self.write_data(0x62)
        
        self.write_cmd(0x36)
        self.write_data(0x28)
        
    
    def show(self, ys, ye):
        self.write_cmd(0x2A)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0x01)
        self.write_data(0xdf)
        
        self.write_cmd(0x2B)
        self.write_data( (ys>>8) & 0xff )
        self.write_data(ys&0xff)
        self.write_data( (ye>>8) & 0xff )
        self.write_data(ye&0xff)
        
        self.write_cmd(0x2C)
        
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(self.buffer)
#        self.spi.write(self.buffer[0:(ye+1-ys)*self.width])
        self.cs(1)
        
    '''
    def show_up(self):
        self.write_cmd(0x2A)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0x01)
        self.write_data(0xdf)
        
        self.write_cmd(0x2B)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0x9f)
        
        self.write_cmd(0x2C)
        
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(self.buffer)
        self.cs(1)
    '''
    
    '''
    def show_down(self):
        self.write_cmd(0x2A)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0x01)
        self.write_data(0xdf)
        
        self.write_cmd(0x2B)
        self.write_data(0x00)
        self.write_data(0xA0)
        self.write_data(0x01)
        self.write_data(0x3f)
        
        self.write_cmd(0x2C)
        
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(self.buffer)
        self.cs(1)
    '''
        
    def bl_ctrl(self,duty):
        pwm = PWM(Pin(LCD_BL))
        pwm.freq(1000)
        if(duty>=100):
            pwm.duty_u16(65535)
        else:
            pwm.duty_u16(655*duty)
            
            
    def draw_point(self,x,y,color):
        self.write_cmd(0x2A)

        
        self.write_data((x-2)>>8)
        self.write_data((x-2)&0xff)
        self.write_data(x>>8)
        self.write_data(x&0xff)
        
        self.write_cmd(0x2B)
        self.write_data((y-2)>>8)
        self.write_data((y-2)&0xff)
        self.write_data(y>>8)
        self.write_data(y&0xff)
        
        self.write_cmd(0x2C)
        
        self.cs(1)
        self.dc(1)
        self.cs(0)
        for i in range(0,9):
            h_color = bytearray(color>>8)
            l_color = bytearray(color&0xff)
            self.spi.write(h_color)
            self.spi.write(l_color)
        self.cs(1)
        
        
    def touch_get(self): 
        if self.irq() == 0:
            self.spi = SPI(1,5_000_000,sck=Pin(LCD_SCK),mosi=Pin(LCD_MOSI),miso=Pin(LCD_MISO))
            self.tp_cs(0)
            X_Point = 0
            Y_Point = 0
            for i in range(0,3):
                self.spi.write(bytearray([0XD0]))
                Read_date = self.spi.read(2)
                time.sleep_us(10)
                X_Point=X_Point+(((Read_date[0]<<8)+Read_date[1])>>3)
                
                self.spi.write(bytearray([0X90]))
                Read_date = self.spi.read(2)
                Y_Point=Y_Point+(((Read_date[0]<<8)+Read_date[1])>>3)

            X_Point=X_Point/3
            Y_Point=Y_Point/3
            
            self.tp_cs(1) 
            self.spi = SPI(1,60_000_000,sck=Pin(LCD_SCK),mosi=Pin(LCD_MOSI),miso=Pin(LCD_MISO))
            Result_list = [X_Point,Y_Point]
            #print(Result_list)
            return(Result_list)


    ##########################################################################
    ### Return a (X,Y) tuple of coordinate on LCD in pixel
    ###   get: Coordinates value in floating point returned by touchpanel_get
    ##########################################################################
    def touch_pixel_get(self, get):
        if get != None:
            X_Point = int((get[1]-430)*480/3270)
            if(X_Point>480):
#                X_Point = 480
                return(-1, -1)
            elif X_Point<0:
#                X_Point = 0
                return(-1, -1)

            Y_Point = 320-int((get[0]-430)*320/3270)
            if Y_Point>320 or Y_Point<0:
                return(-1, -1)

            return(X_Point, Y_Point)
        else:
            return(-1, -1)


    ##################################################################
    ### Get touch information (coordinates value in floating point)
    ###   get_down:
    ###     TouchLCD_3inch5.GET_TOUCH_UP: Get touch-up point
    ###     TouchLCD_3inch5.GET_TOUCH_DOWN: Get touch-down point
    ###   callback_touch:
    ###     Callback function called just after touch with its info
    ###     or None (need not callback)
    ###   callback_touch:
    ###     Callback function called just after release with its info
    ###     or None (need not callback)
    ##################################################################
    def touchpanel_get(self, get_down, callback_touch, callback_drag, callback_detach):
        get = self.touch_get()
        if not get is None:
            XY = self.touch_pixel_get(get)
            if not callback_touch is None:
                callback_touch(get)
            
            # Sense a touch only
            if get_down == TouchLCD_3inch5.GET_TOUCH:
                return get

            # Sense detach
            get3 = None
            drag_origin = None
            while True:
#                time.sleep(0.2)
                time.sleep(0.01)
                get2 = self.touch_get()
                XY2 = self.touch_pixel_get(get2)
                
                # Detach
                if get2 is None:
                    # Detach and return the coordinate touched
                    if get_down == TouchLCD_3inch5.GET_TOUCH_DOWN:
                        if not callback_detach is None:
                            callback_detach(get, get3)
                        return get
                    # Detach and return the coordinate detached
                    elif get3 is None:
                        if not callback_detach is None:
                            callback_detach(get, get)
                        return get
                    else:
                        if not callback_detach is None:
                            callback_detach(get, get3)
                        return get3

                # Dragging
                elif not get3 is None:
                    if not(callback_drag is None) and XY3 != XY2:
                        # Draggin callback function reject callback (maybe busy)
                        if callback_drag(get, get3 if drag_origin is None else drag_origin, get2) == False:
                            # Retain the dragging origin
                            if drag_origin is None:
                                drag_origin = get3
                        # Draggin callback was accepted
                        else:
                            drag_origin = None

                get3 = get2
                XY3 = XY2
                    
        return None
    