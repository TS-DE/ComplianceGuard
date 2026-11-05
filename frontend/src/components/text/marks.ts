/**
 * 原文标记的数据类型。
 *
 * 单列一个文件是因为 `<script setup>` 里不能有 ES 模块导出：
 * 把 `Mark` 声明在组件内再让页面 import，编译会直接失败。
 */
export interface Mark {
  key: string
  start: number
  end: number
  /** 风险色只有三种；piece 是"切分边界"不是风险态，用中性描边，不占语义色 */
  severity: 'hard' | 'soft' | 'pending' | 'piece'
}
