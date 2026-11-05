import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
// base.css 必须在 EP 之后：它靠 CSS 变量覆盖 EP 主题，顺序颠倒就会被 EP 的默认值盖回去
import './styles/base.css'
// 商家端是第二套视觉系统：变量只挂在 .merchant-shell 上，不会传染给运营端案纸风
import './styles/merchant-tokens.css'
// 动效令牌挂在 :root：EP 弹窗/抽屉 teleport 到 body，挂在 .merchant-shell 下会拿不到变量。
// 管理端不加动效靠纪律（motion-* 工具类只在商家端使用），不靠作用域
import './styles/motion.css'
import App from './App.vue'
import router from './router'
createApp(App).use(createPinia()).use(router).use(ElementPlus, { locale: zhCn }).mount('#app')
