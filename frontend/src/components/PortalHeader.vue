<script setup lang="ts">
/** 门户统一顶栏：品牌 / 应用中心 / 登录态 / 应用切换器。 */
import { computed, onMounted, ref, h } from 'vue'
import { AppIcon, LogoutIcon } from 'tdesign-icons-vue-next'
import { logtoEnabled } from '@/config.ts'
import { currentSub, displayUser, signIn, signOut, type DisplayUser } from '@/services/auth/logto.ts'
import { usePortalStore } from '@/services/portal/store.ts'
import AppLauncher from '@/components/AppLauncher.vue'
import type { PortalApp } from '@/services/portal/api.ts'
import { useAppLaunch } from '@/services/portal/useAppLaunch.ts'

const { state, loadCatalog, loadUserData } = usePortalStore()
const { launch } = useAppLaunch()

const launcherVisible = ref(false)
const sub = ref<string | null>(null)
const user = ref<DisplayUser | null>(null)
const enabled = logtoEnabled()

const displayName = computed(() => user.value?.name || user.value?.email || sub.value?.slice(0, 8) || '')
/** 头像链接：加载失败则清空，回退到用户名文字 */
const avatarUrl = ref('')
const avatarFailed = ref(false)
const accountOptions = [
  { content: '退出登录', value: 'logout', prefixIcon: () => h(LogoutIcon) },
]

onMounted(async () => {
  if (!state.loaded) await loadCatalog()
  if (!enabled) return
  sub.value = await currentSub().catch(() => null)
  if (sub.value) {
    user.value = await displayUser().catch(() => null)
    avatarUrl.value = user.value?.picture || ''
    await loadUserData(true)
  }
})

function onAccountClick(item: { value: string }): void {
  if (item.value === 'logout') void logout()
}

async function login(): Promise<void> {
  try { await signIn() } catch { /* 跳转失败保持原状 */ }
}
async function logout(): Promise<void> {
  try { await signOut() } catch { /* 忽略 */ }
}
function openApp(app: PortalApp): void {
  void launch(app)
}
</script>

<template>
  <header class="topbar portal-topbar">
    <router-link :to="{ name: 'home' }" class="brand no-underline">
      <span class="text-brand">AlsoApps</span>
    </router-link>

    <div class="sp"></div>

    <t-button size="small" variant="text" title="应用切换器" @click="launcherVisible = true">
      <AppIcon size="18px" />
    </t-button>

    <template v-if="enabled">
      <t-dropdown v-if="sub" :options="accountOptions" @click="onAccountClick">
        <t-avatar
          v-if="avatarUrl && !avatarFailed"
          size="32px"
          class="cursor-pointer"
          :image="avatarUrl"
          :title="displayName"
          @error="avatarFailed = true"
        />
        <t-avatar
          v-else
          shape="round"
          class="cursor-pointer !w-auto !px-2.5 !text-[12px]"
          :title="displayName"
        >{{ displayName }}</t-avatar>
      </t-dropdown>
      <t-button v-else theme="primary" shape="round" variant="base" @click="login">
        登录
      </t-button>
    </template>

    <AppLauncher v-model:visible="launcherVisible" @launch="openApp" />
  </header>
</template>
