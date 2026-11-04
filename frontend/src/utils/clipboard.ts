/**
 * 复制到剪贴板。
 *
 * 为什么不用裸 navigator.clipboard：它只在 HTTPS 或 localhost 可用，
 * 而本项目要能在内网 http:// 下演示；此时退回 textarea + execCommand，
 * 保证同一个按钮在任何部署环境都能用。
 */
export async function copyText(text: string): Promise<boolean> {
  if (!text) return false
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // 落到下面的兜底方案，不向上抛：复制失败不该打断用户操作。
  }
  try {
    const area = document.createElement('textarea')
    area.value = text
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    const done = document.execCommand('copy')
    document.body.removeChild(area)
    return done
  } catch {
    return false
  }
}
