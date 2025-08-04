"""
LED测试模块
提供多种预设LED闪烁模式，支持独立测试和演示功能
"""

import machine
import time

class LEDTester:
    """LED测试器类"""
    
    def __init__(self, pins=[12, 13]):
        """
        初始化LED测试器
        
        Args:
            pins: LED引脚列表，默认为[12, 13]
        """
        self.pins = pins
        self.leds = []
        self._init_leds()
        
    def _init_leds(self):
        """初始化LED引脚"""
        for pin in self.pins:
            try:
                led = machine.Pin(pin, machine.Pin.OUT)
                led.off()
                self.leds.append(led)
                print(f"LED引脚 {pin} 初始化成功")
            except Exception as e:
                print(f"LED引脚 {pin} 初始化失败: {e}")
                self.leds.append(None)
    
    def _led_on(self, led_index=0, delay=0):
        """打开LED"""
        if led_index < len(self.leds) and self.leds[led_index]:
            self.leds[led_index].on()
            if delay > 0:
                time.sleep(delay)
                
    def _led_off(self, led_index=0, delay=0):
        """关闭LED"""
        if led_index < len(self.leds) and self.leds[led_index]:
            self.leds[led_index].off()
            if delay > 0:
                time.sleep(delay)
    
    def _flash_single(self, led_index=0, on_time=0.1, off_time=0.1):
        """单个LED闪烁一次"""
        self._led_on(led_index, on_time)
        self._led_off(led_index, off_time)
    
    def test_all_leds(self):
        """测试所有LED是否正常工作"""
        print("开始测试所有LED...")
        for i, led in enumerate(self.leds):
            if led:
                print(f"测试LED {i} (引脚 {self.pins[i]})")
                led.on()
                time.sleep(0.5)
                led.off()
                time.sleep(0.3)
            else:
                print(f"LED {i} (引脚 {self.pins[i]}) 未初始化")
        print("LED测试完成")
    
    def quick_flash_three(self, led_index=0):
        """快闪三下模式"""
        print(f"LED {led_index} 快闪三下模式")
        for _ in range(3):
            self._flash_single(led_index, 0.1, 0.1)
        time.sleep(0.3)
    
    def one_long_two_short(self, led_index=0):
        """一长两短模式"""
        print(f"LED {led_index} 一长两短模式")
        self._flash_single(led_index, 0.8, 0.2)
        for _ in range(2):
            self._flash_single(led_index, 0.2, 0.2)
        time.sleep(0.3)
    
    def sos_pattern(self, led_index=0):
        """SOS求救信号模式 (··· --- ···)"""
        print(f"LED {led_index} SOS模式")
        # 三短
        for _ in range(3):
            self._flash_single(led_index, 0.2, 0.2)
        time.sleep(0.3)
        # 三长
        for _ in range(3):
            self._flash_single(led_index, 0.6, 0.2)
        time.sleep(0.3)
        # 三短
        for _ in range(3):
            self._flash_single(led_index, 0.2, 0.2)
        time.sleep(0.5)
    
    def heartbeat(self, led_index=0, cycles=3):
        """心跳模式"""
        print(f"LED {led_index} 心跳模式 ({cycles}次)")
        for _ in range(cycles):
            self._flash_single(led_index, 0.1, 0.1)
            time.sleep(0.3)
            self._flash_single(led_index, 0.1, 0.9)
    
    def police_lights(self, cycles=3):
        """警灯模式（双LED交替闪烁）"""
        if len(self.leds) < 2:
            print("需要至少2个LED才能运行警灯模式")
            return
            
        print(f"警灯模式 ({cycles}次)")
        for _ in range(cycles):
            for _ in range(3):
                self._led_on(0, 0.1)
                self._led_off(0, 0.1)
            for _ in range(3):
                self._led_on(1, 0.1)
                self._led_off(1, 0.1)
    
    def knight_rider(self, cycles=2):
        """霹雳游侠模式（来回扫描）"""
        if len(self.leds) < 2:
            print("需要至少2个LED才能运行霹雳游侠模式")
            return
            
        print(f"霹雳游侠模式 ({cycles}次)")
        for _ in range(cycles):
            # 从左到右
            for i in range(len(self.leds)):
                if self.leds[i]:
                    self._led_on(i, 0.1)
                    self._led_off(i, 0.05)
            # 从右到左
            for i in range(len(self.leds)-1, -1, -1):
                if self.leds[i]:
                    self._led_on(i, 0.1)
                    self._led_off(i, 0.05)
    
    def counting_blink(self, led_index=0, count=5):
        """计数闪烁模式"""
        print(f"LED {led_index} 计数闪烁模式 (1-{count})")
        for i in range(1, count + 1):
            for _ in range(i):
                self._flash_single(led_index, 0.1, 0.1)
            time.sleep(0.4)
    
    def breathing_light(self, led_index=0, cycles=3):
        """呼吸灯模式"""
        print(f"LED {led_index} 呼吸灯模式 ({cycles}次)")
        for _ in range(cycles):
            # 渐亮
            for i in range(10):
                if led_index < len(self.leds) and self.leds[led_index]:
                    # 由于ESP32-C3的GPIO不支持PWM，用短闪烁模拟
                    if i < 5:
                        self._flash_single(led_index, 0.01, 0.09)
                    else:
                        self._flash_single(led_index, 0.05, 0.05)
            time.sleep(0.2)
    
    def demo_all_patterns(self):
        """演示所有模式"""
        print("开始LED模式演示...")
        
        # 测试所有LED
        self.test_all_leds()
        time.sleep(1)
        
        # 单个LED模式演示
        for i in range(min(len(self.leds), 2)):  # 最多演示前2个LED
            print(f"\n=== LED {i} 模式演示 ===")
            self.quick_flash_three(i)
            time.sleep(0.5)
            
            self.one_long_two_short(i)
            time.sleep(0.5)
            
            self.sos_pattern(i)
            time.sleep(0.5)
            
            self.heartbeat(i, 2)
            time.sleep(0.5)
            
            self.counting_blink(i, 3)
            time.sleep(0.5)
            
            self.breathing_light(i, 2)
            time.sleep(1)
        
        # 双LED模式演示
        if len(self.leds) >= 2:
            print("\n=== 双LED模式演示 ===")
            self.police_lights(2)
            time.sleep(1)
            
            self.knight_rider(2)
            time.sleep(1)
        
        print("\nLED模式演示完成")
    
    def custom_pattern(self, pattern, led_index=0):
        """
        自定义模式
        
        Args:
            pattern: 模式列表，每个元素是(亮的时间, 灭的时间)
            led_index: LED索引
        """
        print(f"LED {led_index} 自定义模式")
        for on_time, off_time in pattern:
            self._flash_single(led_index, on_time, off_time)

def main():
    """主函数 - 运行LED测试演示"""
    print("LED测试模块启动")
    
    # 创建LED测试器实例
    led_tester = LEDTester([12, 13])
    
    # 运行完整演示
    led_tester.demo_all_patterns()
    
    print("LED测试模块结束")

if __name__ == "__main__":
    main()