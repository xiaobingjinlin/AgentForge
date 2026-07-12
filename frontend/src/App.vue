<script setup lang="ts">
import ChatPanel from "./components/ChatPanel.vue";
</script>

<template>
  <main class="app-shell">
    <ChatPanel />
  </main>
</template>

<style scoped>
.app-shell {
  width: 100%;
  min-height: 100vh;
}
</style>
