<script setup lang="ts">
/** 门户统一顶栏：品牌 / 应用中心 / 登录态 / 应用切换器。 */
import { computed, onMounted, ref } from 'vue'
import { AppIcon, LogoutIcon, UserIcon } from 'tdesign-icons-vue-next'
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

onMounted(async () => {
  if (!state.loaded) await loadCatalog()
  if (!enabled) return
  sub.value = await currentSub().catch(() => null)
  if (sub.value) {
    user.value = await displayUser().catch(() => null)
    await loadUserData(true)
  }
})

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
      <t-button v-if="sub" size="small" variant="text" @click="logout">
        <LogoutIcon /> <span class="hidden sm:inline">{{ displayName }}</span>
      </t-button>
      <t-button v-else size="small" variant="outline" @click="login">
        <UserIcon /> 登录
      </t-button>
    </template>

    <AppLauncher v-model:visible="launcherVisible" @launch="openApp" />
  </header>
</template>
