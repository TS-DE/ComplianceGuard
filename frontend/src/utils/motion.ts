/**
 * 动效小工具：只操作 DOM 表现，不含任何业务判断。
 * 对应样式与关键帧在 styles/motion.css；系统"减少动效"时自动降级为无动画。
 */

const PULSE_CLASS = 'motion-pulse'

/** 当前环境是否要求减少动效（SSR / 无 matchMedia 时按"不减少"处理）。 */
function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * 分段进入的延迟。
 * @param index 第几个元素（从 0 开始）
 * @param step 相邻元素间隔毫秒，默认 80
 * @returns 可直接用于 animation-delay 的字符串，如 "160ms"
 */
export function stagger(index: number, step = 80): string {
  const safeIndex = Number.isFinite(index) && index > 0 ? Math.floor(index) : 0
  return `${safeIndex * step}ms`
}

/** 把元素平滑滚动到可视区中央；减少动效时直接跳转。 */
export function smoothCenter(el: Element | null | undefined): void {
  if (!el) return
  el.scrollIntoView({
    behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    block: 'center'
  })
}

const pulseTimers = new WeakMap<Element, ReturnType<typeof setTimeout>>()

/**
 * 背景闪一次：加类名，ms 后移除。连续触发时会重新播放而不是被吞掉。
 * @param el 目标元素
 * @param ms 类名保留时长，默认 300
 */
export function pulse(el: Element | null | undefined, ms = 300): void {
  if (!el) return
  const pending = pulseTimers.get(el)
  if (pending) clearTimeout(pending)
  el.classList.remove(PULSE_CLASS)
  // 读一次布局强制重排，确保同一元素再次添加类名时动画会重新开始
  void (el as HTMLElement).offsetWidth
  el.classList.add(PULSE_CLASS)
  pulseTimers.set(el, setTimeout(() => {
    el.classList.remove(PULSE_CLASS)
    pulseTimers.delete(el)
  }, ms))
}
