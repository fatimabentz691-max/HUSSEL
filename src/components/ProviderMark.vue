<script setup lang="ts">
import { computed } from 'vue'
import anthropic from '../assets/providers/official/anthropic.png?url'
import baichuan from '../assets/providers/official/baichuan.ico?url'
import deepseek from '../assets/providers/official/deepseek.png?url'
import doubao from '../assets/providers/official/doubao.png?url'
import gemini from '../assets/providers/official/gemini.svg?url'
import hunyuan from '../assets/providers/official/hunyuan.ico?url'
import kimi from '../assets/providers/official/kimi.ico?url'
import mimo from '../assets/providers/official/mimo.png?url'
import minimax from '../assets/providers/official/minimax.ico?url'
import openai from '../assets/providers/official/openai.svg?url'
import qianfan from '../assets/providers/official/qianfan.ico?url'
import qwen from '../assets/providers/official/qwen.svg?url'
import sensenova from '../assets/providers/official/sensenova.png?url'
import spark from '../assets/providers/official/spark.ico?url'
import stepfun from '../assets/providers/official/stepfun.svg?url'
import yi from '../assets/providers/official/yi.svg?url'
import zhipu from '../assets/providers/official/zhipu.png?url'

interface LogoDefinition {
  src: string
  /** 宽版官方字标需要稍微缩小，保证完整显示且不被裁切。 */
  fit?: 'symbol' | 'wordmark'
}

const props = defineProps<{ name: string }>()

/**
 * 只映射各平台官方网站或官方代码仓库公开的原始品牌资源。
 * 黑白效果由 CSS 显示层完成，不重新描摹、变形或裁切官方图形。
 */
const logos: Record<string, LogoDefinition> = {
  '腾讯混元': { src: hunyuan },
  '豆包（火山方舟）': { src: doubao },
  '文心千帆': { src: qianfan },
  '通义百炼': { src: qwen },
  '智谱 AI': { src: zhipu },
  DeepSeek: { src: deepseek },
  Kimi: { src: kimi },
  '讯飞星火': { src: spark },
  MiniMax: { src: minimax },
  '阶跃星辰': { src: stepfun },
  '零一万物': { src: yi },
  '商汤日日新': { src: sensenova },
  '百川智能': { src: baichuan },
  OpenAI: { src: openai },
  Anthropic: { src: anthropic },
  'Google Gemini': { src: gemini },
  '小米 MiMo': { src: mimo, fit: 'wordmark' },
  '自定义 OpenAI 兼容': { src: openai },
}

const logo = computed(() => logos[props.name])
</script>

<template>
  <span class="provider-mark" :title="`${name} · 官方品牌资源`">
    <img
      v-if="logo"
      :src="logo.src"
      :alt="`${name} 官方商标`"
      :class="{ 'is-wordmark': logo.fit === 'wordmark' }"
      draggable="false"
    >
    <span v-else class="provider-mark__missing" aria-hidden="true">—</span>
  </span>
</template>

<style scoped>
.provider-mark {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #dedede;
  border-radius: 10px;
  background: #fff;
  flex: 0 0 auto;
  overflow: hidden;
}

.provider-mark img {
  width: 24px;
  height: 24px;
  object-fit: contain;
  object-position: center;
  filter: grayscale(1) contrast(4);
  user-select: none;
}

.provider-mark img.is-wordmark {
  width: 28px;
  height: 15px;
}

.provider-mark__missing {
  color: #1d1d1f;
  font-size: 14px;
  line-height: 1;
}
</style>
