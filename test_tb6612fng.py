# 利民TL-S12W风扇引脚诊断脚本 (ESP32-C3)
# 帮助确定PWM和TACH的正确连接

from machine import Pin, PWM
import machine, time
import sys
try:
    import uselect
except ImportError:
    uselect = None

# 测试用的引脚
TEST_PINS = [6, 2]  # 您当前连接的两个引脚
PWM_FREQ = 25000
PULSES_PER_REV = 2  # 风扇TACH默认2脉冲/转, 利民TL-S12W实测为2脉冲/转
MIN_TACH_INTERVAL_US = 12000  # 脉冲去抖最小间隔(微秒), 提升至12000us有效过滤高频噪声与PWM谐波干扰
# 新增: 低速起转辅助（防止卡死）
KICKSTART_PERCENT = 50
KICKSTART_MS = 500
# 新增: 保存TACH相邻脉冲间隔用于“周期法”计算RPM
INTERVALS_MAX_LEN = 20
_intervals = {p: [] for p in TEST_PINS}

# 脉冲计数变量, 基于 TEST_PINS 动态初始化
_pulse_counts = {p: 0 for p in TEST_PINS}
_last_pulse_time = {p: 0 for p in TEST_PINS}


def _make_irq_handler(pin_num):
    """为每个引脚创建IRQ处理函数"""
    def handler(pin):
        global _pulse_counts, _last_pulse_time
        now = time.ticks_us()
        # 简单防抖 + 记录间隔(用于周期法)
        last = _last_pulse_time.get(pin_num, 0)
        if last > 0:
            dt = time.ticks_diff(now, last)
            if dt < MIN_TACH_INTERVAL_US:  # 使用更长的最小脉冲间隔, 抑制高频噪声误触发
                return
            # 记录有效间隔
            buf = _intervals.get(pin_num)
            if buf is not None:
                buf.append(dt)
                if len(buf) > INTERVALS_MAX_LEN:
                    del buf[0]
        _last_pulse_time[pin_num] = now
        # 防止键不存在
        if pin_num not in _pulse_counts:
            _pulse_counts[pin_num] = 0
        _pulse_counts[pin_num] += 1
    return handler


def reset_pulse_counters():
    """重置所有脉冲计数"""
    global _pulse_counts, _last_pulse_time
    state = machine.disable_irq()
    for pin_num in TEST_PINS:
        _pulse_counts[pin_num] = 0
        _last_pulse_time[pin_num] = 0
        _intervals[pin_num] = []
    machine.enable_irq(state)

# 新增: 基于脉冲间隔的RPM计算（周期法, 更稳更快）

def rpm_from_intervals(pin_num, min_samples=3):
    buf = _intervals.get(pin_num, [])
    if len(buf) < min_samples:
        return None
    
    # 使用IQR方法过滤离群值
    take = min(10, len(buf))
    sample = sorted(buf[-take:])
    
    # 计算Q1和Q3
    q1_idx = len(sample) // 4
    q3_idx = 3 * len(sample) // 4
    q1 = sample[q1_idx]
    q3 = sample[q3_idx]
    iqr = q3 - q1
    
    # 过滤异常值（1.5*IQR规则）
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    filtered = [x for x in sample if lower_bound <= x <= upper_bound]
    
    if not filtered:
        return None
    
    # 使用过滤后的中位数
    median_us = filtered[len(filtered) // 2]
    if median_us <= 0:
        return None
    
    rpm = int(60000000 / (median_us * PULSES_PER_REV))
    
    # 额外检查RPM合理性（风扇最高2000RPM）
    if rpm > 2000:
        return None
    
    return rpm

# 新增: 交互暂停的安全等待函数, 清空输入缓冲后再等待一次回车

def wait_enter(prompt=""):
    """等待用户按回车, 并清空可能残留的输入缓冲避免立即返回"""
    if uselect is not None:
        try:
            poll = uselect.poll()
            poll.register(sys.stdin, uselect.POLLIN)
            # 清空缓冲区, 防止上一轮输入的换行直接触发
            while True:
                events = poll.poll(0)
                if not events:
                    break
                try:
                    sys.stdin.read(1)
                except Exception:
                    break
        except Exception:
            pass
    try:
        input(prompt)
    except EOFError:
        # 某些环境下不支持交互输入, 退化为短暂等待
        print(prompt)
        time.sleep(1)


def test_pin_as_pwm(pin_num, other_pin_num, open_drain=False):
    """测试某个引脚作为PWM输出
    open_drain: True表示使用开漏模式模拟PWM（仅支持0%或100%两档, 中间占空比无法用软件精确模拟25kHz）
    """
    mode_str = "开漏模拟" if open_drain else "标准"
    print(f"\n=== 测试GPIO{pin_num}作为{mode_str}PWM, GPIO{other_pin_num}作为TACH ===")
    
    try:
        # 设置PWM输出
        if open_drain:
            # 开漏模式: 使用普通GPIO开漏输出, 仅支持0%/100%两档
            pwm_pin = Pin(pin_num, Pin.OUT_OD)
            def set_open_drain_pwm(percent):
                if percent <= 0:
                    pwm_pin.value(0)  # 拉低=0%
                elif percent >= 100:
                    pwm_pin.value(1)  # 释放=100%（由外部上拉）
                else:
                    # 无法产生连续25kHz开漏PWM, 仅近似为就近的0/100
                    pwm_pin.value(1 if percent >= 50 else 0)
        else:
            # 标准PWM模式
            pwm = PWM(Pin(pin_num), freq=PWM_FREQ)
        
        # 设置TACH输入
        tach_pin = Pin(other_pin_num, Pin.IN, Pin.PULL_UP)
        tach_pin.irq(trigger=Pin.IRQ_FALLING, handler=_make_irq_handler(other_pin_num))
        
        # 测试不同PWM值
        test_pwm_values = [0, 30, 60, 100]
        
        for pwm_percent in test_pwm_values:
            print(f"\n--- PWM设置为 {pwm_percent}% ---")
            
            # 设置PWM
            if open_drain:
                if 0 < pwm_percent < 100:
                    print("提示: 开漏模式当前仅支持 0% 或 100% 两档, 将近似为就近值")
                set_open_drain_pwm(pwm_percent)
            else:
                if hasattr(pwm, "duty_u16"):
                    pwm.duty_u16(int(65535 * pwm_percent / 100))
                else:
                    pwm.duty(int(1023 * pwm_percent / 100))
            
            print(f"已设置GPIO{pin_num} PWM为 {pwm_percent}%")
            if pwm_percent == 0:
                print("注意: PWM 0%可能不等于完全停止, 请确认风扇是否支持停转功能")
            
            # 等待风扇稳定
            time.sleep(2)
            
            # 重置计数器并测量
            reset_pulse_counters()
            print("测量3秒内的脉冲...")
            time.sleep_ms(3000)
            
            # 读取结果
            state = machine.disable_irq()
            pulses = _pulse_counts.get(other_pin_num, 0)
            machine.enable_irq(state)
            
            # 计算RPM
            window_sec = 3
            rpm = int((pulses * (60 / window_sec)) / PULSES_PER_REV)
            rpm2 = rpm_from_intervals(other_pin_num)
            
            print(f"GPIO{other_pin_num}检测到 {pulses} 个脉冲")
            if rpm2 is not None:
                print(f"计算转速(周期法): {rpm2} RPM | (计数法): {rpm} RPM")
            else:
                print(f"计算转速: {rpm} RPM")
            
            # 判断是否合理（以计数法为基准的阈值）
            if 0 <= rpm <= 2000:
                print("✓ 转速读数（计数法）在合理范围内")
            else:
                print("✗ 转速读数（计数法）异常, 可能有干扰或PPR设置不正确")
        
        # 清理
        if open_drain:
            pwm_pin.value(0)  # 确保拉低
        else:
            pwm.duty_u16(0) if hasattr(pwm, "duty_u16") else pwm.duty(0)
            pwm.deinit()
        tach_pin.irq(handler=None)
        
    except Exception as e:
        print(f"测试出错: {e}")
        return False
    
    return True


def diagnostic_full():
    """完整诊断: 测试两种引脚配置"""
    print("=== 利民TL-S12W风扇引脚诊断 ===")
    print("将测试两种可能的引脚配置...")
    print("请确保风扇已正确连接电源（+12V和GND）")
    wait_enter("按回车键开始诊断...")
    
    a, b = TEST_PINS[0], TEST_PINS[1]
    
    # 测试标准PWM模式
    print("\n" + "="*50)
    print("首先测试标准PWM模式:")
    
    # 配置1: a=PWM, b=TACH
    print(f"配置1测试：GPIO{a}=PWM输出, GPIO{b}=TACH输入")
    test_pin_as_pwm(a, b, False)
    
    time.sleep(2)
    
    # 配置2: b=PWM, a=TACH  
    print(f"配置2测试：GPIO{b}=PWM输出, GPIO{a}=TACH输入")
    test_pin_as_pwm(b, a, False)
    
    # 测试开漏PWM模式
    print("\n" + "="*50)
    print("现在测试开漏模拟PWM模式:")
    print("说明: 仅支持0%/100%两档, 中间占空比无法用软件精确模拟25kHz, 仅用于验证布线与上拉是否正确")
    
    # 配置1: a=PWM, b=TACH
    print(f"配置1测试：GPIO{a}=开漏PWM输出, GPIO{b}=TACH输入")
    test_pin_as_pwm(a, b, True)
    
    time.sleep(2)
    
    # 配置2: b=PWM, a=TACH  
    print(f"配置2测试：GPIO{b}=开漏PWM输出, GPIO{a}=TACH输入")
    test_pin_as_pwm(b, a, True)
    
    print("\n=== 诊断总结 ===")
    print("请观察哪种配置和模式下：")
    print("1. 转速随PWM%正常变化（PWM越高转速越高）")
    print("2. 转速数值在合理范围内（0-2000 RPM）")
    print("3. 没有异常高的脉冲计数")
    print("\n正确的配置应该显示合理的转速变化。")


def simple_tach_test():
    """简单TACH信号测试"""
    print("\n=== 简单TACH信号测试 ===")
    print("此测试不使用PWM, 只检测哪个引脚有转速信号")
    
    a, b = TEST_PINS[0], TEST_PINS[1]
    # 同时监听两个引脚
    pin_a = Pin(a, Pin.IN, Pin.PULL_UP)
    pin_b = Pin(b, Pin.IN, Pin.PULL_UP)
    
    pin_a.irq(trigger=Pin.IRQ_FALLING, handler=_make_irq_handler(a))
    pin_b.irq(trigger=Pin.IRQ_FALLING, handler=_make_irq_handler(b))
    
    print(f"开始监听GPIO{a}和GPIO{b}的脉冲信号...")
    print("请手动给风扇通电, 或确保风扇在运行...")
    
    for i in range(5):
        reset_pulse_counters()
        print(f"\n第{i+1}次测量 (2秒)...")
        time.sleep_ms(2000)
        
        state = machine.disable_irq()
        pulses_a = _pulse_counts.get(a, 0)
        pulses_b = _pulse_counts.get(b, 0)
        machine.enable_irq(state)
        
        print(f"GPIO{a}: {pulses_a} 脉冲, GPIO{b}: {pulses_b} 脉冲")
        
        # 计算RPM
        window_sec = 2
        rpm_a = int((pulses_a * (60 / window_sec)) / PULSES_PER_REV) if pulses_a > 0 else 0
        rpm_b = int((pulses_b * (60 / window_sec)) / PULSES_PER_REV) if pulses_b > 0 else 0
        
        print(f"GPIO{a}计算转速: {rpm_a} RPM")
        print(f"GPIO{b}计算转速: {rpm_b} RPM")
    
    pin_a.irq(handler=None)
    pin_b.irq(handler=None)
    
    print("\n有稳定脉冲信号的引脚就是TACH引脚")


def interactive_pwm_monitor():
    """交互式PWM控制与连续转速监测
    - 默认使用配置1: TEST_PINS[0] 作为 PWM, TEST_PINS[1] 作为 TACH
    - 支持在运行中调整 PWM 百分比, 并以 1s 周期持续输出转速
    - 输入帮助: 直接输入 0-100 设置占空比; 输入 q 退出; 输入 h 查看帮助; 输入 s 交换一次 PWM/TACH 引脚
    - 输入 o 切换开漏/标准PWM模式
    - 输入 ppr N 设置每转脉冲数; 输入 deb N(us) 设置防抖阈值; 输入 freq N(Hz) 设置PWM频率
    """
    global PULSES_PER_REV, MIN_TACH_INTERVAL_US
    print("\n=== 交互式PWM控制与连续转速监测 ===")
    a, b = TEST_PINS[0], TEST_PINS[1]
    pwm_pin_num, tach_pin_num = a, b
    open_drain_mode = False
    
    print(f"默认使用配置1: GPIO{pwm_pin_num}=PWM, GPIO{tach_pin_num}=TACH")
    print("模式: 标准PWM")
    print("指令: 输入 0-100 设置PWM%; 输入 s 交换PWM与TACH; 输入 o 切换开漏模式; 输入 ppr N; 输入 deb N; 输入 freq N; 输入 h 查看帮助; 输入 q 退出")

    # 工具函数: 设置PWM占空比
    def _apply_pwm_percent(pwm_obj, percent, open_drain=False):
        percent = max(0, min(100, int(percent)))
        if open_drain:
            # 开漏模式仅支持0/100两档, 中间值近似
            if percent <= 0:
                pwm_pin.value(0)  # 拉低
            elif percent >= 100:
                pwm_pin.value(1)  # 高阻态
            else:
                pwm_pin.value(1 if percent >= 50 else 0)
        else:
            if hasattr(pwm_obj, "duty_u16"):
                pwm_obj.duty_u16(int(65535 * percent / 100))
            else:
                pwm_obj.duty(int(1023 * percent / 100))
        return percent

    # 初始化外设
    if open_drain_mode:
        pwm_pin = Pin(pwm_pin_num, Pin.OUT_OD)
        pwm = None
    else:
        pwm = PWM(Pin(pwm_pin_num), freq=PWM_FREQ)
        pwm_pin = None
    
    tach_pin = Pin(tach_pin_num, Pin.IN, Pin.PULL_UP)
    tach_pin.irq(trigger=Pin.IRQ_FALLING, handler=_make_irq_handler(tach_pin_num))

    current_percent = 30
    current_percent = _apply_pwm_percent(pwm if not open_drain_mode else pwm_pin, current_percent, open_drain_mode)
    print(f"已设置初始PWM {current_percent}% 在 GPIO{pwm_pin_num}")

    if uselect is None:
        print("注意: 设备不支持非阻塞输入, 将持续打印转速, 请用 Ctrl+C 退出")

    # 连续监测循环
    last_print = time.ticks_ms()
    try:
        while True:
            # 每 1s 计算一次转速
            now = time.ticks_ms()
            if time.ticks_diff(now, last_print) >= 1000:
                last_print = now
                state = machine.disable_irq()
                pulses = _pulse_counts.get(tach_pin_num, 0)
                _pulse_counts[tach_pin_num] = 0  # 清零用于下一窗口
                machine.enable_irq(state)
                window_sec = 1
                rpm_cnt = int((pulses * (60 / window_sec)) / PULSES_PER_REV)
                rpm_per = rpm_from_intervals(tach_pin_num)
                mode_str = "开漏" if open_drain_mode else "标准"
                
                # 计数法合理性检查
                if rpm_cnt > 2000:  # 风扇物理上限
                    print(f"PWM={current_percent}% ({mode_str}) | GPIO{tach_pin_num} 脉冲={pulses} | 异常转速={rpm_cnt} RPM (超过风扇物理上限)")
                else:
                    if rpm_per is not None:
                        print(f"PWM={current_percent}% ({mode_str}) | GPIO{tach_pin_num} 脉冲={pulses} | 转速={rpm_per} RPM(周期法) / {rpm_cnt} RPM(计数法)")
                    else:
                        print(f"PWM={current_percent}% ({mode_str}) | GPIO{tach_pin_num} 脉冲={pulses} | 估算转速={rpm_cnt} RPM")

            # 非阻塞读取指令
            if uselect is not None:
                try:
                    poll = uselect.poll()
                    poll.register(sys.stdin, uselect.POLLIN)
                    events = poll.poll(0)
                    if events:
                        line = sys.stdin.readline().strip()
                        if not line:
                            pass
                        elif line.lower() == "q":
                            print("退出交互式监测")
                            break
                        elif line.lower() == "h":
                            print("输入 0-100 设置PWM%; 输入 s 交换PWM与TACH; 输入 o 切换开漏模式; 输入 ppr N; 输入 deb N(us); 输入 freq N(Hz); 输入 q 退出")
                        elif line.lower() == "o":
                            # 切换开漏模式
                            open_drain_mode = not open_drain_mode
                            
                            # 清理旧PWM
                            if pwm is not None:
                                _apply_pwm_percent(pwm, 0, False)
                                pwm.deinit()
                                pwm = None
                            if pwm_pin is not None:
                                pwm_pin.value(0)
                            
                            # 重新初始化
                            if open_drain_mode:
                                pwm_pin = Pin(pwm_pin_num, Pin.OUT_OD)
                                pwm = None
                                print("切换到开漏PWM模式（仅支持0%/100%两档）")
                            else:
                                pwm = PWM(Pin(pwm_pin_num), freq=PWM_FREQ)
                                pwm_pin = None
                                print("切换到标准PWM模式")
                            
                            # 恢复占空比
                            current_percent = _apply_pwm_percent(pwm if not open_drain_mode else pwm_pin, current_percent, open_drain_mode)
                            reset_pulse_counters()
                        elif line.lower() == "s":
                            # 交换角色
                            tach_pin.irq(handler=None)
                            
                            # 清理旧PWM
                            if pwm is not None:
                                _apply_pwm_percent(pwm, 0, False)
                                pwm.deinit()
                                pwm = None
                            if pwm_pin is not None:
                                pwm_pin.value(0)
                            
                            # 交换引脚
                            pwm_pin_num, tach_pin_num = tach_pin_num, pwm_pin_num
                            
                            # 重新初始化
                            if open_drain_mode:
                                pwm_pin = Pin(pwm_pin_num, Pin.OUT_OD)
                                pwm = None
                            else:
                                pwm = PWM(Pin(pwm_pin_num), freq=PWM_FREQ)
                                pwm_pin = None
                            
                            tach_pin = Pin(tach_pin_num, Pin.IN, Pin.PULL_UP)
                            tach_pin.irq(trigger=Pin.IRQ_FALLING, handler=_make_irq_handler(tach_pin_num))
                            
                            # 恢复占空比
                            current_percent = _apply_pwm_percent(pwm if not open_drain_mode else pwm_pin, current_percent, open_drain_mode)
                            reset_pulse_counters()
                            print(f"已交换: GPIO{pwm_pin_num}=PWM, GPIO{tach_pin_num}=TACH")
                        else:
                            # 解析带参数命令
                            parts = line.split()
                            cmd = parts[0].lower()
                            if cmd in ("ppr", "deb", "freq"):
                                if len(parts) < 2:
                                    print("缺少参数, 用法: ppr N | deb N(us) | freq N(Hz)")
                                else:
                                    try:
                                        val = int(parts[1])
                                    except ValueError:
                                        print("参数必须是整数")
                                        continue
                                    if cmd == "ppr":
                                        if val <= 0 or val > 8:
                                            print("PPR无效, 请输入1-8之间的整数（常见为2或4）")
                                        else:
                                            PULSES_PER_REV = val
                                            reset_pulse_counters()
                                            print(f"已设置PPR={PULSES_PER_REV}")
                                    elif cmd == "deb":
                                        if val < 1000:
                                            print("去抖阈值过小, 建议>=4000us")
                                        MIN_TACH_INTERVAL_US = val
                                        reset_pulse_counters()
                                        print(f"已设置防抖阈值={MIN_TACH_INTERVAL_US}us")
                                    elif cmd == "freq":
                                        if pwm is not None:
                                            try:
                                                pwm.freq(val)
                                                print(f"已设置PWM频率={val}Hz")
                                            except Exception as e:
                                                print(f"设置PWM频率失败: {e}")
                                        else:
                                            print("当前为开漏模式, 频率设置不适用")
                            else:
                                # 尝试解析为占空比
                                try:
                                    val = int(line)
                                    if 0 <= val <= 100:
                                        # 小占空比起转辅助（仅标准PWM模式）
                                        if (not open_drain_mode) and (pwm is not None) and (current_percent == 0) and (0 < val <= 10):
                                            _apply_pwm_percent(pwm, KICKSTART_PERCENT, False)
                                            time.sleep_ms(KICKSTART_MS)
                                        if open_drain_mode and 0 < val < 100:
                                            print("提示: 开漏模式当前仅支持 0% 或 100% 两档, 中间值将近似为就近值")
                                        current_percent = _apply_pwm_percent(pwm if not open_drain_mode else pwm_pin, val, open_drain_mode)
                                        print(f"已设置PWM为 {current_percent}%")
                                    else:
                                        print("请输入 0-100 的整数占空比或指令 h 查看帮助")
                                except ValueError:
                                    print("无效输入, 请输入 0-100 的整数或指令 h")
                except Exception:
                    # 输入错误不影响采样
                    pass
            # 轻微延时避免忙等
            time.sleep_ms(50)
    except KeyboardInterrupt:
        print("收到中断, 即将退出")
    finally:
        # 清理
        try:
            if pwm is not None:
                _apply_pwm_percent(pwm, 0, False)
                pwm.deinit()
            if pwm_pin is not None:
                pwm_pin.value(0)
        except Exception:
            pass
        try:
            tach_pin.irq(handler=None)
        except Exception:
            pass
        print("已退出交互式监测\n")


def main():
    print("=== 利民TL-S12W风扇诊断工具 ===")
    print("1) 完整引脚配置诊断 (包含开漏PWM测试)")
    print("2) 简单TACH信号检测")
    print("3) 交互式PWM控制与连续转速监测 (支持开漏模式)")
    print("0) 退出")
    
    while True:
        choice = input("\n请选择诊断方式: ").strip()
        
        if choice == "0":
            break
        elif choice == "1":
            diagnostic_full()
        elif choice == "2":
            simple_tach_test()
        elif choice == "3":
            interactive_pwm_monitor()
        else:
            print("无效选择")
    
    print("诊断完成")


if __name__ == "__main__":
    main()
