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
  min-height: 100vh;
  padding: 0;
  display: block;
}
</style>
