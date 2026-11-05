import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
// base.css 必须在 EP 之后：它靠 CSS 变量覆盖 EP 主题，顺序颠倒就会被 EP 的默认值盖回去
import './styles/base.css'
import App from './App.vue'
import router from './router'
createApp(App).use(createPinia()).use(router).use(ElementPlus, { locale: zhCn }).mount('#app')
