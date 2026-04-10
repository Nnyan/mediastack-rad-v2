<template>
  <div v-if="open" style="position:absolute;inset:0;background:rgba(0,0,0,0.6);display:flex;align-items:flex-start;justify-content:center;padding-top:60px;z-index:200;min-height:500px">
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;width:100%;max-width:680px;overflow:hidden">
      <div style="padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px">
        <span style="font-family:var(--mono);font-size:13px;font-weight:600;flex:1">Add application</span>
        <button class="btn btn-sm" @click="$emit('close')">✕ Close</button>
      </div>

      <div style="padding:16px 18px">
        <div style="display:flex;gap:0;margin-bottom:16px;border:1px solid var(--border);border-radius:6px;overflow:hidden">
          <button :class="['btn',tab==='paste'?'btn-primary':'']" style="flex:1;border:none;border-radius:0" @click="tab='paste'">Paste compose YAML</button>
          <button :class="['btn',tab==='github'?'btn-primary':'']" style="flex:1;border:none;border-radius:0;border-left:1px solid var(--border)" @click="tab='github'">GitHub URL</button>
        </div>

        <div v-if="tab==='paste'">
          <p style="font-size:11px;color:var(--muted);margin-bottom:8px">Paste the contents of a docker-compose.yml file</p>
          <textarea
            v-model="yamlText"
            style="width:100%;min-height:200px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-family:var(--mono);font-size:11px;padding:10px;resize:vertical;line-height:1.6;outline:none"
            placeholder="services:&#10;  myapp:&#10;    image: myimage:latest&#10;    ports:&#10;      - &quot;8080:80&quot;"
          />
          <div style="margin-top:10px;display:flex;justify-content:flex-end">
            <button class="btn btn-primary btn-sm" :disabled="!yamlText.trim() || loading" @click="doParse">
              <span v-if="loading" class="spinner" style="width:11px;height:11px" /> Parse
            </button>
          </div>
        </div>

        <div v-if="tab==='github'">
          <p style="font-size:11px;color:var(--muted);margin-bottom:8px">
            Enter a GitHub repo URL or a direct link to a compose file
          </p>
          <div style="display:flex;gap:8px">
            <input
              v-model="githubUrl"
              class="search"
              style="flex:1;max-width:none"
              placeholder="https://github.com/user/repo"
              @keyup.enter="doGithub"
            />
            <button class="btn btn-primary btn-sm" :disabled="!githubUrl.trim() || loading" @click="doGithub">
              <span v-if="loading" class="spinner" style="width:11px;height:11px" /> Fetch
            </button>
          </div>
          <div style="margin-top:8px;font-size:11px;color:var(--muted)">
            Accepts: repo root, blob URL, or raw URL. Searches for docker-compose.yml automatically.
          </div>
        </div>

        <div v-if="error" style="margin-top:12px;padding:10px 12px;background:#da363318;border:1px solid var(--danger);border-radius:6px;color:#ff8080;font-size:12px">
          {{ error }}
        </div>

        <div v-if="services.length" style="margin-top:14px">
          <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);margin-bottom:8px">
            Found {{ services.length }} service(s)
          </div>
          <div style="display:grid;gap:8px;max-height:280px;overflow-y:auto">
            <div v-for="svc in services" :key="svc.name"
              style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:10px 12px">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                <span style="font-family:var(--mono);font-size:12px;font-weight:600">{{ svc.name }}</span>
                <span class="badge" :class="`badge-${svc.status||'running'}`" style="font-size:9px">{{ svc.category }}</span>
              </div>
              <div style="font-family:var(--mono);font-size:11px;color:var(--muted);margin-bottom:6px">{{ svc.image }}:{{ svc.tag }}</div>
              <div style="display:flex;gap:6px;flex-wrap:wrap">
                <span v-for="p in svc.ports.slice(0,4)" :key="p" class="port-pill">{{ p }}</span>
                <span v-if="svc.depends_on.length" style="font-size:10px;color:var(--muted)">
                  needs: {{ svc.depends_on.join(', ') }}
                </span>
              </div>
            </div>
          </div>

          <div style="margin-top:14px;padding:12px;background:#388bfd15;border:1px solid var(--info-border,#388bfd40);border-radius:6px">
            <div style="font-size:11px;font-weight:600;color:var(--info,#388bfd);margin-bottom:6px">How to deploy these services</div>
            <div style="font-size:11px;color:var(--muted);line-height:1.7">
              Save the compose file to your server, then run:<br>
              <code style="display:block;margin-top:6px;padding:6px 10px;background:var(--bg);border-radius:4px;font-size:10px">
                docker compose -f /path/to/docker-compose.yml up -d
              </code>
              The containers will appear in the dashboard automatically on the next refresh.
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { API } from "@/composables/useApi.js";

const props = defineProps({ open: Boolean });
const emit = defineEmits(["close"]);

const tab      = ref("paste");
const yamlText = ref("");
const githubUrl = ref("");
const services = ref([]);
const error    = ref(null);
const loading  = ref(false);

async function doParse() {
  error.value = null;
  services.value = [];
  loading.value = true;
  try {
    const res = await API.compose.parse(yamlText.value);
    services.value = res.services;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function doGithub() {
  error.value = null;
  services.value = [];
  loading.value = true;
  try {
    const res = await API.compose.github(githubUrl.value);
    services.value = res.services;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
</script>
