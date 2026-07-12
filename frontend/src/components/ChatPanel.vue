<script setup lang="ts">
import { nextTick, onMounted, ref } from "vue";
import {
  createProject,
  createSession,
  exportProject,
  fetchMessages,
  healthCheck,
  streamChat,
  type ChatMessage,
  type DomainResult,
} from "../api/client";

const projectId = ref("");
const sessionId = ref("");
const input = ref("");
const messages = ref<ChatMessage[]>([]);
const domainResults = ref<DomainResult[]>([]);
const selectedDomain = ref<DomainResult | null>(null);
const streaming = ref(false);
const statusText = ref("初始化中...");
const errorText = ref("");
const templateStack = ref<string[]>(["base"]);
const exportHint = ref("");
const listRef = ref<HTMLElement | null>(null);

async function scrollToBottom() {
  await nextTick();
  if (listRef.value) {
    listRef.value.scrollTop = listRef.value.scrollHeight;
  }
}

async function bootstrap() {
  try {
    const ok = await healthCheck();
    if (!ok) throw new Error("后端健康检查失败");
    const project = await createProject("demo-project");
    projectId.value = project.id;
    const session = await createSession(project.id, "对话会话");
    sessionId.value = session.id;
    statusText.value = `已连接 · Spring Boot ${project.framework_version ?? "4.0"}`;
  } catch (err) {
    errorText.value = err instanceof Error ? err.message : String(err);
    statusText.value = "连接失败";
  }
}

async function reloadMessages() {
  if (!sessionId.value) return;
  messages.value = await fetchMessages(sessionId.value);
  await scrollToBottom();
}

async function sendMessage() {
  const text = input.value.trim();
  if (!text || !sessionId.value || streaming.value) return;

  input.value = "";
  streaming.value = true;
  errorText.value = "";
  domainResults.value = [];
  selectedDomain.value = null;
  messages.value.push({ role: "user", content: text });
  const assistantIndex = messages.value.length;
  messages.value.push({ role: "assistant", content: "" });
  await scrollToBottom();

  try {
    await streamChat(sessionId.value, text, {
      onStatus: (data) => {
        statusText.value = String(data.message ?? "处理中...");
        const stack = data.template_stack as string[] | undefined;
        if (stack?.length) templateStack.value = stack;
      },
      onCapabilityEnabled: (data) => {
        const cap = String(data.capability_id ?? "");
        const stack = data.template_stack as string[] | undefined;
        if (stack?.length) templateStack.value = stack;
        const generated = Boolean(data.generated);
        exportHint.value = generated
          ? `LLM 已生成并启用: ${cap}`
          : data.already_enabled
            ? `能力层 ${cap} 已在项目中`
            : `已自动启用能力层: ${cap}`;
      },
      onCapabilityGenerating: (data) => {
        statusText.value = String(data.message ?? `正在生成 ${data.capability_id}...`);
      },
      onCapabilityGenerated: (data) => {
        exportHint.value = `能力层 ${data.capability_id} 已入库: ${data.path ?? ""}`;
      },
      onDomainResult: async (data) => {
        domainResults.value.push(data);
        if (!selectedDomain.value) selectedDomain.value = data;
      },
      onToken: async (token) => {
        messages.value[assistantIndex].content += token;
        await scrollToBottom();
      },
      onDone: (data) => {
        const stack = data.template_stack as string[] | undefined;
        if (stack?.length) templateStack.value = stack;
        const files = data.sandbox_files as string[] | undefined;
        if (files?.length) {
          exportHint.value = `沙盒 ${files.length} 个文件 · 栈: ${templateStack.value.join(" + ")}`;
        }
      },
      onError: (message) => {
        errorText.value = message;
      },
    });
    await reloadMessages();
    statusText.value = "就绪";
  } catch (err) {
    errorText.value = err instanceof Error ? err.message : String(err);
    messages.value.pop();
  } finally {
    streaming.value = false;
  }
}

async function handleExport() {
  if (!projectId.value) return;
  try {
    const result = await exportProject(projectId.value);
    exportHint.value = `落盘完成: ${result.target_path} (${result.files_copied} 文件)`;
    if (result.hint) exportHint.value += ` · ${result.hint}`;
  } catch (err) {
    errorText.value = err instanceof Error ? err.message : String(err);
  }
}

function selectDomain(item: DomainResult) {
  selectedDomain.value = item;
}

onMounted(() => {
  bootstrap();
});
</script>

<template>
  <div class="layout">
    <section class="chat-panel">
      <header class="chat-header">
        <div class="brand">
          <h1>AgentForge</h1>
          <p class="subtitle">Spring Boot 对话式编程</p>
        </div>
        <div class="header-meta">
          <span class="status">{{ statusText }}</span>
          <span v-if="templateStack.length" class="stack">栈: {{ templateStack.join(" + ") }}</span>
        </div>
      </header>

      <div ref="listRef" class="message-list">
        <div
          v-for="(msg, index) in messages"
          :key="index"
          class="message"
          :class="msg.role"
        >
          <div class="role">{{ msg.role === "user" ? "你" : "Agent" }}</div>
          <pre class="content">{{ msg.content }}</pre>
        </div>
        <p v-if="!messages.length" class="empty">
          发送一条需求开始，例如：生成 Order 模块完整 CRUD
        </p>
      </div>

      <div v-if="errorText" class="error">{{ errorText }}</div>
      <div v-if="exportHint" class="hint">{{ exportHint }}</div>

      <footer class="composer">
        <textarea
          v-model="input"
          rows="3"
          placeholder="描述你想生成的 Spring Boot 模块..."
          :disabled="streaming || !sessionId"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <div class="actions">
          <button :disabled="streaming || !sessionId || !input.trim()" @click="sendMessage">
            {{ streaming ? "生成中..." : "发送" }}
          </button>
          <button
            class="secondary"
            :disabled="!projectId || streaming"
            @click="handleExport"
          >
            一键落盘
          </button>
        </div>
      </footer>
    </section>

    <aside class="preview-panel">
      <h2>代码预览</h2>
      <div v-if="domainResults.length" class="domain-tabs">
        <button
          v-for="item in domainResults"
          :key="item.domain"
          class="tab"
          :class="{ active: selectedDomain?.domain === item.domain }"
          @click="selectDomain(item)"
        >
          {{ item.domain }}
        </button>
      </div>
      <div v-if="selectedDomain" class="code-preview">
        <p class="file-path">{{ selectedDomain.file_path }}</p>
        <p class="summary">{{ selectedDomain.summary }}</p>
        <pre class="code-block">{{ selectedDomain.code_preview }}</pre>
      </div>
      <p v-else class="empty-preview">生成后将在此展示各域代码预览</p>
    </aside>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  width: 100%;
  min-height: 100vh;
  background: #0f1419;
}

.chat-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 100vh;
  padding: 16px 20px;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  background: #121821;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-shrink: 0;
  margin-bottom: 12px;
}

.brand h1 {
  margin: 0;
  font-size: 1.35rem;
}

.subtitle {
  margin: 4px 0 0;
  color: #8b98a8;
  font-size: 0.9rem;
}

.header-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.status {
  color: #7dd3a8;
  font-size: 0.85rem;
}

.stack {
  font-size: 0.75rem;
  color: #8b98a8;
}

.message-list {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  padding-right: 4px;
}

.message {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.message.user {
  background: rgba(56, 120, 255, 0.12);
}

.message.assistant {
  background: rgba(125, 211, 168, 0.08);
}

.role {
  font-size: 0.75rem;
  color: #8b98a8;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.content {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.92rem;
}

.empty {
  color: #8b98a8;
  text-align: center;
  margin: auto 0;
}

.error {
  color: #ff8f8f;
  font-size: 0.9rem;
  flex-shrink: 0;
}

.hint {
  padding: 0.5rem 0;
  color: #7dd3a8;
  font-size: 0.85rem;
  flex-shrink: 0;
}

.composer {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
  margin-top: 12px;
}

.actions {
  display: flex;
  gap: 0.5rem;
}

button.secondary {
  background: #475569;
}

.preview-panel {
  min-height: 100vh;
  padding: 16px;
  background: #0b1016;
  overflow: auto;
}

.preview-panel h2 {
  margin: 0 0 0.75rem;
  font-size: 1rem;
  color: #e8edf5;
}

.domain-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.75rem;
}

.tab {
  padding: 0.25rem 0.6rem;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 999px;
  background: transparent;
  color: #cbd5e1;
  cursor: pointer;
  font-size: 0.8rem;
}

.tab.active {
  background: #2563eb;
  color: #fff;
  border-color: #2563eb;
}

.code-preview .file-path {
  font-size: 0.8rem;
  color: #94a3b8;
  word-break: break-all;
}

.code-preview .summary {
  font-size: 0.85rem;
  color: #cbd5e1;
  margin: 0.5rem 0;
}

.code-block {
  background: #111827;
  color: #e2e8f0;
  padding: 0.75rem;
  border-radius: 8px;
  font-size: 0.75rem;
  overflow: auto;
  max-height: calc(100vh - 180px);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.empty-preview {
  color: #64748b;
  font-size: 0.9rem;
}

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr auto;
  }

  .chat-panel {
    min-height: 60vh;
    border-right: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .preview-panel {
    min-height: 40vh;
  }
}
</style>
