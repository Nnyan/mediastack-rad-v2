<template>
  <div class="builder">

    <!-- ── Header ──────────────────────────────────────────────────────── -->
    <div class="builder-header">
      <div>
        <h1 class="page-title">Stack Builder</h1>
        <div class="header-sub">
          <span>{{ selectedServices.length }} service{{ selectedServices.length !== 1 ? 's' : '' }} selected</span>
          <span v-if="req.domain" class="header-sub-sep">·</span>
          <span v-if="req.domain">{{ req.domain }}</span>
        </div>
      </div>
      <div class="header-actions">
        <div class="search-wrap">
          <span class="search-icon">🔍</span>
          <input v-model="search" placeholder="Search services…" class="search-input" />
        </div>
        <button class="btn-review" :disabled="previewLoading || !selectedServices.length" @click="preview">
          {{ previewLoading ? 'Generating…' : 'Review' }}
        </button>
        <button class="primary" :disabled="deploying || !selectedServices.length" @click="deploy">
          {{ deploying ? 'Deploying…' : 'Deploy stack →' }}
        </button>
      </div>
    </div>

    <!-- ── Two-column layout: config left, grid right ───────────────────── -->
    <div class="builder-layout">

      <!-- Left: config accordion -->
      <div class="config-panel">
        <div class="config-area">

          <div class="cfg-section" :class="{ open: expanded.core }">
          <div class="cfg-head cfg-head-pinned">
            <span class="cfg-icon">⚙️</span>
            <span class="cfg-title">Core settings</span>
          </div>
          <div v-if="expanded.core" class="cfg-body">
            <div class="cfg-grid">
              <label class="cfg-field span2">
                <span class="cfg-label">Domain</span>
                <input v-model="req.domain" placeholder="nyrdalyrt.com" :readonly="isFieldFromLive('domain')" :class="{ 'cfg-readonly': isFieldFromLive('domain') }" />
                <span class="cfg-hint">Apps served as sonarr.{{ req.domain || 'example.com' }}</span>
              </label>
              <label class="cfg-field span2">
                <span class="cfg-label">Config root</span>
                <input v-model="req.config_root" placeholder="/home/stack/mediacenter/config" />
              </label>
              <label class="cfg-field">
                <span class="cfg-label">Media root</span>
                <input v-model="req.media_root" placeholder="/mnt/media" />
                <span class="cfg-hint">Mounted as /data inside containers</span>
              </label>
              <label class="cfg-field">
                <span class="cfg-label">Timezone</span>
                <input v-model="req.timezone" placeholder="America/Los_Angeles" :readonly="isFieldFromLive('timezone')" :class="{ 'cfg-readonly': isFieldFromLive('timezone') }" />
              </label>
              <label class="cfg-field">
                <span class="cfg-label">PUID</span>
                <input v-model.number="req.puid" type="number" />
              </label>
              <label class="cfg-field">
                <span class="cfg-label">PGID</span>
                <input v-model.number="req.pgid" type="number" />
              </label>
            </div>
          </div>
          </div>

          <!-- Cloudflare — only when traefik or cloudflared is selected -->
                    <template v-if="pick['traefik'] || pick['cloudflared']">
          <div class="cfg-section" :class="{ open: expanded.cloudflare }">
          <div class="cfg-head" @click="toggleCfg('cloudflare')">
            <span class="cfg-icon">☁️</span>
            <span class="cfg-title">Cloudflare</span>
          </div>
          <div v-if="expanded.cloudflare" class="cfg-body">
            <div class="cfg-grid">
              <label v-if="pick['traefik']" class="cfg-field span2">
                <span class="cfg-label">
                  DNS API Token
                  <a href="https://dash.cloudflare.com/profile/api-tokens" target="_blank" class="cfg-link">Create ↗</a>
                </span>
                <input v-model="req.cloudflare_token" type="password" placeholder="CF_DNS_API_TOKEN — Zone:DNS:Edit + Zone:Zone:Read" :readonly="isFieldFromLive('cloudflare_token')" :class="{ 'cfg-readonly': isFieldFromLive('cloudflare_token') }" />
                <span class="cfg-hint">Required for DNS-01 HTTPS cert issuance via Traefik</span>
              </label>
              <label v-if="pick['cloudflared']" class="cfg-field span2">
                <span class="cfg-label">
                  Tunnel Token
                  <a href="https://one.dash.cloudflare.com/" target="_blank" class="cfg-link">Zero Trust ↗</a>
                </span>
                <input v-model="req.cloudflare_tunnel_token" type="password" placeholder="CLOUDFLARED_TOKEN from Zero Trust → Tunnels" :readonly="isFieldFromLive('cloudflare_tunnel_token')" :class="{ 'cfg-readonly': isFieldFromLive('cloudflare_tunnel_token') }" />
                <span class="cfg-hint">Authenticates the cloudflared daemon to your tunnel</span>
              </label>
            </div>
          </div>
          </div>
          </template>

          <!-- Tailscale — only when tailscale is selected -->
                    <template v-if="pick['tailscale']">
          <div class="cfg-section" :class="{ open: expanded.tailscale }">
          <div class="cfg-head" @click="toggleCfg('tailscale')">
            <span class="cfg-icon">🔗</span>
            <span class="cfg-title">Tailscale</span>
          </div>
          <div v-if="expanded.tailscale" class="cfg-body">
            <div class="cfg-grid">
              <label class="cfg-field span2">
                <span class="cfg-label">
                  Auth key
                  <a href="https://login.tailscale.com/admin/settings/keys" target="_blank" class="cfg-link">Tailscale admin ↗</a>
                </span>
                <input v-model="req.tailscale_auth_key" type="password" placeholder="tskey-auth-… (reusable, non-ephemeral)" :readonly="isFieldFromLive('tailscale_auth_key')" :class="{ 'cfg-readonly': isFieldFromLive('tailscale_auth_key') }" />
                <span class="cfg-hint">Generate a reusable, non-ephemeral key — ephemeral keys expire and drop the node.</span>
              </label>
              <label class="cfg-field">
                <span class="cfg-label">Node hostname</span>
                <input v-model="req.tailscale_hostname" placeholder="mediastack" :readonly="isFieldFromLive('tailscale_hostname')" :class="{ 'cfg-readonly': isFieldFromLive('tailscale_hostname') }" />
                <span class="cfg-hint">How this server appears in your tailnet</span>
              </label>
              <label class="cfg-field">
                <span class="cfg-label">Subnet routes</span>
                <input v-model="req.tailscale_routes" placeholder="172.20.0.0/16" :readonly="isFieldFromLive('tailscale_routes')" :class="{ 'cfg-readonly': isFieldFromLive('tailscale_routes') }" />
                <span class="cfg-hint">Docker network CIDR — gives enrolled devices direct container access</span>
              </label>
            </div>
          </div>
          </div>
          </template>

          <!-- Tinyauth — only when tinyauth is selected -->
                    <template v-if="pick['tinyauth']">
          <div class="cfg-section" :class="{ open: expanded.tinyauth }">
          <div class="cfg-head" @click="toggleCfg('tinyauth')">
            <span class="cfg-icon">🔒</span>
            <span class="cfg-title">Tinyauth</span>
          </div>
          <div v-if="expanded.tinyauth" class="cfg-body">
            <div class="cfg-note cfg-note-purple">
              🔒 <strong>LAN users ({{ req.lan_subnet }}) pass through automatically.</strong>
              Only Tailscale and internet traffic is challenged.
            </div>
            <div class="cfg-grid">
              <label class="cfg-field">
                <span class="cfg-label">LAN subnet</span>
                <input v-model="req.lan_subnet" placeholder="10.0.0.0/22" :readonly="isFieldFromLive('lan_subnet')" :class="{ 'cfg-readonly': isFieldFromLive('lan_subnet') }" />
                <span class="cfg-hint">Devices in this CIDR bypass Tinyauth entirely</span>
              </label>
              <label class="cfg-field">
                <span class="cfg-label">App URL</span>
                <input v-model="req.tinyauth_app_url" placeholder="https://auth.nyrdalyrt.com" :readonly="isFieldFromLive('tinyauth_app_url')" :class="{ 'cfg-readonly': isFieldFromLive('tinyauth_app_url') }" />
                <span class="cfg-hint">⚠ Must be added as a public hostname in your CF Tunnel → forward to http://tinyauth:3000</span>
              </label>

              <label class="cfg-field span2">
                <span class="cfg-label">
                  Users
                  <button class="gen-btn" type="button" @click="generateCredentials">Generate admin</button>
                </span>
                <input v-model="req.tinyauth_users" placeholder="admin:$2b$10$..." :readonly="isFieldFromLive('tinyauth_users')" :class="{ 'cfg-readonly': isFieldFromLive('tinyauth_users') }" />
                <span class="cfg-hint">Format: <code>username:bcrypt_hash</code> — click Generate admin or separate multiple users with commas</span>
              </label>
              <div v-if="generatedPassword" class="generated-password-box">
                <span class="gen-pw-label">
                  ⚠ Save this — not shown again
                  <button class="gen-pw-dismiss" @click="generatedPassword = ''">✕ dismiss</button>
                </span>
                <code class="gen-pw-value">{{ generatedPassword }}</code>
              </div>

            </div>
          </div>
          </div>
          </template>

          <!-- Plex — only when plex is selected -->
          <template v-if="pick['plex']">
          <div class="cfg-section" :class="{ open: expanded.plex }">
          <div class="cfg-head" @click="toggleCfg('plex')">
            <span class="cfg-icon">🎬</span>
            <span class="cfg-title">Plex</span>
            <span class="cfg-badge-mode">{{ plexMode === 'local' ? 'new server' : 'existing server' }}</span>
          </div>
          <div v-if="expanded.plex" class="cfg-body">
            <div class="mode-toggle">
              <button :class="['mode-btn', { active: plexMode === 'local' }]" @click="plexMode = 'local'">New Plex server</button>
              <button :class="['mode-btn', { active: plexMode === 'external' }]" @click="plexMode = 'external'">Link existing server</button>
            </div>

            <!-- New Plex server -->
            <div v-show="plexMode === 'local'">
              <div class="cfg-grid">
                <label class="cfg-field">
                  <span class="cfg-label">Server name</span>
                  <input v-model="req.plex_server_name" placeholder="My Plex Server" />
                  <span class="cfg-hint">Friendly name shown in Plex clients</span>
                </label>
                <label class="cfg-field">
                  <span class="cfg-label">
                    Plex Claim Token
                    <a href="https://plex.tv/claim" target="_blank" class="cfg-link">Get one ↗</a>
                  </span>
                  <input v-model="req.plex_claim" type="password" placeholder="claim-xxxxxxxxxxxxxxxxxxxx" />
                  <span class="cfg-hint">Links this server to your Plex account on first boot. Expires in 4 minutes — generate it just before deploying.</span>
                </label>
                <label class="cfg-field">
                  <span class="cfg-label">
                    X-Plex-Token
                    <a href="https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/" target="_blank" class="cfg-link">How to find ↗</a>
                  </span>
                  <input v-model="req.plex_token" type="password" placeholder="xxxxxxxxxxxxxxxxxxxx" :readonly="isFieldFromLive('plex_token')" :class="{ 'cfg-readonly': isFieldFromLive('plex_token') }" />
                  <span class="cfg-hint">Your personal Plex auth token. Used by Sonarr, Radarr, Prowlarr and other apps to authenticate with this Plex server.</span>
                </label>
              </div>
            </div>

            <!-- Existing Plex server -->
            <div v-show="plexMode === 'external'">
              <div class="cfg-note cfg-note-info" style="margin-bottom: var(--space-3)">
                Plex will not be added to this stack. The IP address and token below will be passed to Sonarr, Radarr, Prowlarr, Bazarr and Seerr so they can connect to your existing server.
              </div>
              <div class="cfg-grid">
                <label class="cfg-field span2">
                  <span class="cfg-label">Plex server URL</span>
                  <input v-model="req.plex_url" placeholder="http://192.168.1.50:32400" />
                  <span class="cfg-hint">Use the local LAN IP for best performance. Port is usually 32400.</span>
                </label>
                <label class="cfg-field span2">
                  <span class="cfg-label">
                    X-Plex-Token
                    <a href="https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/" target="_blank" class="cfg-link">How to find ↗</a>
                  </span>
                  <input v-model="req.plex_token" type="password" placeholder="xxxxxxxxxxxxxxxxxxxx" />
                  <span class="cfg-hint">Your personal Plex auth token. In Plex Web: Settings → Troubleshooting → Show → X-Plex-Token. Passed to Sonarr, Radarr, Prowlarr, Bazarr and Seerr.</span>
                </label>
              </div>
            </div>

          </div>
          </div>
          </template>

          <!-- Add custom app — always visible below Core settings -->
          <div class="cfg-section" :class="{ open: expanded.custom }">
           <div class="cfg-head" @click="toggleCfg('custom')">
             <span class="cfg-icon">📦</span>
             <span class="cfg-title">Add custom app</span>
          </div>
          <div v-if="expanded.custom" class="cfg-body">
            <div class="tab-row">
              <button
                v-for="[t, label] in [['compose','Compose YAML'],['url','Image URL'],['file','Upload']]"
                :key="t" :class="['tab-btn', { active: addTab === t }]" @click="addTab = t"
              >{{ label }}</button>
            </div>
            <template v-if="addTab === 'compose'">
              <p class="cfg-hint custom-hint">Paste a <code>docker-compose.yml</code> fragment — it will be parsed and merged into your stack.</p>
              <textarea v-model="addInput" class="compose-textarea" placeholder="services:
  myapp:
    image: ghcr.io/author/myapp:latest
    ports:
      - &quot;8123:8123&quot;"></textarea>
            </template>
            <template v-else-if="addTab === 'url'">
              <p class="cfg-hint custom-hint">Enter a Docker Hub image name or full registry URL. Sensible defaults will be generated.</p>
              <input v-model="addInput" placeholder="lscr.io/linuxserver/heimdall  or  portainer/portainer-ce" class="url-input" />
            </template>
            <template v-else>
              <div class="file-drop" @click="fileInput?.click()" @dragover.prevent @drop.prevent="onFileDrop">
                <div class="file-drop-icon">📄</div>
                <div class="file-drop-title">Drop a compose file here</div>
                <div class="file-drop-sub">or click to browse — .yml and .yaml supported</div>
                <div v-if="addFileName" class="file-drop-name">{{ addFileName }}</div>
              </div>
              <input ref="fileInput" type="file" accept=".yml,.yaml" style="display:none" @change="onFilePick" />
            </template>
            <!-- Parse result preview -->
            <div v-if="addResult" class="parse-result">
              <div class="parse-result-head">
                <span class="parse-result-title">
                  {{ addResult.services.length }} service{{ addResult.services.length !== 1 ? 's' : '' }} found
                </span>
                <button class="parse-confirm" @click="confirmCustomApp">
                  ✓ Add to stack
                </button>
              </div>
              <div v-for="svc in addResult.services" :key="svc.name" class="parse-svc">
                <span class="parse-svc-name">{{ svc.name }}</span>
                <span class="parse-svc-image">{{ svc.image }}</span>
                <span v-for="p in svc.ports" :key="p" class="parse-svc-port">{{ p }}</span>
              </div>
              <div v-if="customYaml" class="parse-confirmed">
                ✓ Will be included in next deploy
              </div>
            </div>

            <div class="custom-actions">
              <button class="btn-review" :disabled="addParsing" @click="parseAndAdd">
                {{ addParsing ? 'Fetching…' : 'Parse & add' }}
              </button>
            </div>
          </div>
          </div>

          <!-- Per-service extra env vars — shown when any service is selected -->
          <div v-if="selectedServices.length" class="cfg-section" :class="{ open: expanded.extraenv }">
          <div class="cfg-head" @click="toggleCfg('extraenv')">
            <span class="cfg-icon">🔧</span>
            <span class="cfg-title">Variables</span>
          </div>
          <div v-if="expanded.extraenv" class="cfg-body">
            <p class="cfg-hint" style="margin: 6px 0 10px; font-style: normal; font-size: 11px;">
              Add arbitrary environment variables to any selected service.
              These are merged last and override catalog defaults.
            </p>
            <div v-for="key in selectedServices" :key="key" class="extraenv-service">
              <div class="extraenv-service-head" @click="toggleExtraEnv(key)">
                <span class="extraenv-icon">{{ svcByKey[key]?.icon || '📦' }}</span>
                <span class="extraenv-name">{{ svcName(key) }}</span>
                <span v-if="(extraEnvRows[key]||[]).filter(r=>r.k).length"
                  class="extraenv-count">{{ (extraEnvRows[key]||[]).filter(r=>r.k).length }} var{{ (extraEnvRows[key]||[]).filter(r=>r.k).length !== 1 ? 's' : '' }}</span>
                <span class="extraenv-chevron" :class="{ open: extraEnvOpen[key] }">›</span>
              </div>
              <div v-if="extraEnvOpen[key]" class="extraenv-rows">
                <div v-for="(row, idx) in (extraEnvRows[key] ||= [])" :key="idx" class="extraenv-row">
                  <input v-model="row.k" placeholder="VAR_NAME" class="extraenv-key" @keydown.tab.prevent="addEnvRow(key)" />
                  <span class="extraenv-eq">=</span>
                  <input v-model="row.v" placeholder="value" class="extraenv-val" />
                  <button class="extraenv-rm" @click="removeEnvRow(key, idx)">✕</button>
                </div>
                <button class="extraenv-add" @click="addEnvRow(key)">+ Add variable</button>
              </div>
            </div>
          </div>
          </div>


        </div>
      </div><!-- /config-panel -->

      <!-- Right: services + instances -->
      <div class="grid-panel">

        <div class="card tile-card">
          <div class="tile-header">
            <div>
              <h3 class="tile-title">Service Catalog</h3>
            </div>
            <div class="search-wrap tile-search">
              <span class="search-icon">🔍</span>
              <input v-model="search" placeholder="Search services…" class="search-input" />
            </div>
          </div>

          <div class="service-grid" :style="{ '--tile-min-width': tileMinWidth + 'px' }">
            <button
              v-for="svc in filteredServices"
              :key="svc.key"
              :class="['tile', tileClass(svc.key)]"
              @click="toggle(svc.key)"
            >
              <span class="tile-icon">{{ svc.icon }}</span>
              <span class="tile-name">{{ svc.display_name }}</span>
              <span class="tile-status">
                <span v-if="liveServices.has(svc.key)" class="tile-dot dot-ok">●</span>
                <span v-else-if="pick[svc.key]" class="tile-dot dot-err">●</span>
                <span v-else class="tile-dot dot-off">●</span>
              </span>
            </button>
          </div>

          <div v-if="portConflicts.length" class="port-conflict-banner">
            <div class="port-conflict-banner-head">
              <span class="port-conflict-icon">⚠</span>
              <span class="port-conflict-title">{{ portConflicts.length }} port conflict{{ portConflicts.length !== 1 ? 's' : '' }} detected</span>
              <span v-if="portsChecking" class="port-conflict-checking">checking…</span>
            </div>
            <div v-for="c in portConflicts" :key="c.service" class="port-conflict-row">
              <span class="port-conflict-svc">{{ svcName(c.service) }}</span>
              <span class="port-conflict-detail">
                port <strong>{{ c.port }}</strong> already used by
                <code>{{ c.conflict_with }}</code>
              </span>
              <button class="port-conflict-accept" @click="acceptPortSuggestion(c)">
                Use {{ c.suggested_port }}
              </button>
            </div>
          </div>
        </div>

        <div class="card instances-card">
          <div class="instances-header">
            <div>
              <h3 class="instances-title">Running Instances</h3>
            </div>
            <div class="instances-controls">
              <div class="search-wrap instances-search">
                <span class="search-icon">🔍</span>
                <input v-model="containerSearch" placeholder="Search containers…" class="search-input" />
              </div>
              <label class="toggle-stopped">
                <input type="checkbox" v-model="showStoppedContainers" />
                <span>Show stopped</span>
              </label>
            </div>
          </div>

          <div class="instances-list">
            <div
              v-for="c in filteredContainers"
              :key="c.id"
              :class="['instance-card', instanceCardState(c), { selected: selectedContainerId === c.id }]"
              @click="selectContainer(c.id)"
            >
              <div class="instance-top">
                <span class="instance-dot" :class="containerDotClass(c)"></span>
                <span class="instance-icon" :class="{ link: !!containerUrls[c.id] }">
                  {{ containerIcon(c.name) }}
                </span>
                <button
                  v-if="containerUrls[c.id]"
                  class="instance-name has-link"
                  @click.stop="openContainer(containerUrls[c.id])"
                >{{ formatContainerName(c.name) }}</button>
                <span v-else class="instance-name">{{ formatContainerName(c.name) }}</span>
              </div>
              <div class="instance-bottom">
                <div class="instance-actions" @click.stop>
                  <button
                    class="icon-btn"
                    :title="c.state === 'running' ? 'Stop' : 'Start'"
                    @click="containerAction(c.name, c.state === 'running' ? 'stop' : 'start')"
                  >{{ c.state === 'running' ? '⏸' : '▶' }}</button>
                  <button class="icon-btn" title="Restart" @click="containerAction(c.name, 'restart')">↺</button>
                  <button class="icon-btn" title="Logs" @click="loadLogs(c.name)">≡</button>
                  <button class="icon-btn danger" title="Remove" @click="confirmRemove(c.name)">✕</button>
                </div>
              </div>
            </div>
            <div v-if="!filteredContainers.length" class="instances-empty">No containers yet.</div>
          </div>

          <div v-if="selectedContainer" class="instance-detail">
            <div class="detail-header">
              <div>
                <div class="detail-name">{{ formatContainerName(selectedContainer.name) }}</div>
                <div class="detail-meta">
                  <span class="detail-status">{{ containerStatusLabel(selectedContainer) }}</span>
                  <span class="detail-metrics">{{ containerMetrics(selectedContainer, true) }}</span>
                </div>
              </div>
              <button class="icon-btn" @click="clearSelection">✕</button>
            </div>
            <div class="detail-grid">
              <div>
                <span class="detail-label">Image</span>
                <span class="detail-value mono">{{ shortImage(selectedContainer.image) }}</span>
              </div>
              <div>
                <span class="detail-label">Created</span>
                <span class="detail-value">{{ createdTime(selectedContainer) }}</span>
              </div>
              <div>
                <span class="detail-label">Ports</span>
                <span class="detail-value">{{ containerPorts(selectedContainer) }}</span>
              </div>
              <div>
                <span class="detail-label">Status</span>
                <span class="detail-value">{{ containerStatusLabel(selectedContainer) }}</span>
              </div>
            </div>
            <div class="detail-actions">
              <button class="icon-btn" title="Restart" @click.stop="containerAction(selectedContainer.name, 'restart')">↺</button>
              <button
                class="icon-btn"
                :title="selectedContainer.state === 'running' ? 'Stop' : 'Start'"
                @click.stop="containerAction(selectedContainer.name, selectedContainer.state === 'running' ? 'stop' : 'start')"
              >{{ selectedContainer.state === 'running' ? '⏸' : '▶' }}</button>
              <button class="icon-btn" title="Refresh logs" @click.stop="loadLogs(selectedContainer.name)">≡</button>
            </div>
            <pre v-if="containerLogs && containerLogsName === selectedContainer.name" class="detail-logs mono">{{ containerLogs }}</pre>
            <div v-else-if="containerLogsLoading" class="detail-logs muted">Loading logs…</div>
          </div>
        </div>

      </div><!-- /grid-panel -->

    </div><!-- /builder-layout -->

    <!-- ── Preview output ───────────────────────────────────────────────── -->
    <div v-if="previewText" class="deploy-output-area">
      <div v-if="previewWarnings.length" class="preview-warnings">
        <div v-for="w in previewWarnings" :key="w.message" class="preview-warn-row">
          <span class="preview-warn-icon">⚠</span>
          <span class="preview-warn-svc" v-if="w.service">{{ w.service }}</span>
          <span class="preview-warn-msg">{{ w.message }}</span>
        </div>
      </div>
      <div class="output-block ok">
        <div class="output-label">Generated compose ({{ previewText.length }} bytes)</div>
        <pre class="output">{{ previewText }}</pre>
      </div>
    </div>

    <!-- ── Deploy output ────────────────────────────────────────────────── -->
    <div v-if="deployOutput" class="deploy-output-area">
      <div :class="['output-block', deployOk ? 'ok' : 'err']">
        <div class="output-label">{{ deployOk ? 'Deploy output' : 'Deploy errors' }}</div>
        <pre class="output">{{ deployOutput }}</pre>
      </div>
      <div v-if="deployConflicts.length" class="conflict-banner">
        <div class="conflict-banner-head">
          <span class="conflict-icon">⚠</span>
          <span class="conflict-title">{{ deployConflicts.length }} container conflict(s)</span>
        </div>
        <div class="conflict-names">
          <span v-for="name in deployConflicts" :key="name" class="conflict-name">{{ name }}</span>
        </div>
        <div class="conflict-actions">
          <span class="conflict-warn">Removing these containers will allow the deploy to proceed.</span>
          <button class="conflict-btn" :disabled="deploying" @click="purgeAndRetry">
            {{ deploying ? 'Purging…' : 'Remove conflicts & retry' }}
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch, inject } from 'vue'

const showToast = inject('showToast')

// ── State ──────────────────────────────────────────────────────────────────
const rawCatalog   = ref({})
localStorage.removeItem('rad-stack-builder-pick')
const pick         = reactive({})
const search       = ref('')
const activeFilter = ref('')
// Plain reactive object — boolean per section. More reliable than reactive(Set)
// because Vue 3 template compiler tracks plain property reads, not Set.has() calls.
const expanded = reactive({
  core: true, cloudflare: false, tailscale: false,
  tinyauth: false, plex: false, custom: false, extraenv: false, deploy: true,
})
const plexMode     = ref('local')
const addTab       = ref('compose')
const addInput     = ref('')
const portOverrides  = reactive({})   // { service_key: override_port }
const extraEnvOpen   = reactive({})   // { service_key: bool } — expand env panel
const extraEnvRows   = reactive({})   // { service_key: [{k:'',v:''},...] }
const portConflicts  = ref([])        // [{service, port, conflict_with, suggested_port}]
const portsChecking  = ref(false)
const addParsing   = ref(false)
const addResult    = ref(null)   // { yaml, services } from backend
const addFileName  = ref('')     // name of uploaded file
const fileInput    = ref(null)   // template ref for hidden <input type="file">
const customYaml   = ref('')     // confirmed YAML to include in deploy
const previewText  = ref('')
const previewLoading = ref(false)
const deployOutput    = ref('')
const deployOk        = ref(false)
const deploying       = ref(false)
const deployConflicts = ref([])   // container names blocking the deploy

// Containers merged view
const containers = ref([])
const stats = ref({})
const containerSearch = ref('')
const showStoppedContainers = ref(false)
const selectedContainerId = ref(null)
const containerLogs = ref('')
const containerLogsName = ref('')
const containerLogsLoading = ref(false)

let containersPollTimer = null
let statsWs = null
let statsWsActive = false

// ── Persistence ────────────────────────────────────────────────────────────
const STORAGE_KEY      = 'rad-stack-builder-v3'
const STORAGE_KEY_PREV = 'rad-stack-builder-v2'
const defaults = {
  domain: '', timezone: 'America/Los_Angeles', puid: 1000, pgid: 1000,
  config_root: '/home/stack/mediacenter/config',
  media_root: '/mnt/media',
  cloudflare_token: '', cloudflare_tunnel_token: '',
  external_plex_url: '',
  plex_server_name: '', plex_claim: '',
  plex_url: '', plex_token: '',
  tailscale_auth_key: '', tailscale_routes: '', tailscale_hostname: 'mediastack',
  tinyauth_users: '', tinyauth_app_url: '',
  lan_subnet: '10.0.0.0/22',
}
// Migrate settings from previous key if v3 is empty
let _stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
if (!_stored || Object.keys(_stored).length === 0) {
  const _prev = JSON.parse(localStorage.getItem(STORAGE_KEY_PREV) || '{}')
  if (Object.keys(_prev).length > 0) {
    _stored = _prev
    localStorage.setItem(STORAGE_KEY, JSON.stringify(_stored))
  }
}
const stored = _stored || {}
const req = reactive({ ...defaults, ...stored })

// Sensitive fields that must never be persisted to localStorage.
const SENSITIVE_FIELDS = new Set([
  'cloudflare_token', 'cloudflare_tunnel_token',
  'tailscale_auth_key', 'tinyauth_users', 'plex_token', 'plex_claim',
])

function sanitizeForStorage(v) {
  const safe = { ...v }
  for (const key of SENSITIVE_FIELDS) {
    delete safe[key]
  }
  return safe
}

watch(req, v => localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitizeForStorage(v))), { deep: true })

// ── Constants ──────────────────────────────────────────────────────────────
const TAG_LABELS = {
  media:       'Media',
  indexers:    'Management',
  downloaders: 'Download',
  requests:    'Requests',
  infra:       'Infrastructure',
}

const CAT_COLORS = {
  media:       { bg: 'rgba(219,39,119,0.07)', border: 'rgba(219,39,119,0.3)', text: 'var(--pink)' },
  indexers:    { bg: 'rgba(124,58,237,0.07)', border: 'rgba(124,58,237,0.3)', text: 'var(--purple)' },
  downloaders: { bg: 'rgba(37,99,235,0.07)',  border: 'rgba(37,99,235,0.3)',  text: 'var(--blue)' },
  requests:    { bg: 'rgba(234,88,12,0.07)',  border: 'rgba(234,88,12,0.3)',  text: 'var(--orange)' },
  infra:       { bg: 'rgba(8,145,178,0.07)',  border: 'rgba(8,145,178,0.3)',  text: 'var(--teal)' },
}

const SHORT_DESCS = {
  plex: 'Media server', jellyfin: 'Open-source media server',
  sonarr: 'TV manager', radarr: 'Movie manager', lidarr: 'Music manager',
  readarr: 'Books & audiobooks', bazarr: 'Subtitle manager', prowlarr: 'Index manager',
  qbittorrent: 'BitTorrent client', sabnzbd: 'Usenet downloader', nzbget: 'Usenet (lite)',
  seerr: 'Request manager (Plex/Jellyfin/Emby)',
  traefik: 'Reverse proxy & HTTPS', tinyauth: 'Auth gateway',
  tailscale: 'Private VPN mesh', cloudflared: 'Public tunnel',
}

const ICONS = {
  plex: '🎬', jellyfin: '🎞️', sonarr: '📺', radarr: '🎥', lidarr: '🎵',
  readarr: '📚', bazarr: '💬', prowlarr: '🔍', qbittorrent: '⬇️',
  sabnzbd: '📰', nzbget: '📥', seerr: '🙋',
  traefik: '🔀', tinyauth: '🔒', tailscale: '🔗', cloudflared: '☁️',
}

// Set for O(1) lookup instead of Array.includes()
// Keyed by container name — assumes container name === service key, which holds
// for compose-managed stacks where the service name is the container name.
const liveServices = ref(new Set())
const liveEnv = ref({})  // { container_name: { KEY: VALUE } }

const ENV_TO_FIELD = {
  PUID: 'puid', PGID: 'pgid', TZ: 'timezone',
  CF_DNS_API_TOKEN: 'cloudflare_token', TUNNEL_TOKEN: 'cloudflare_tunnel_token',
  TS_AUTHKEY: 'tailscale_auth_key', TS_ROUTES: 'tailscale_routes', TS_HOSTNAME: 'tailscale_hostname',
  TINYAUTH_AUTH_USERS: 'tinyauth_users', TINYAUTH_APPURL: 'tinyauth_app_url',
  PLEX_CLAIM: 'plex_claim', PLEX_TOKEN: 'plex_token',
}

async function loadRunningServices() {
  try {
    const running = await fetch('/api/containers/running').then(r => r.json())
    const names = Array.isArray(running) ? running : []
    liveServices.value = new Set(names)
    if (names.length) {
      try {
        const envData = await fetch(`/api/containers/env?names=${names.join(',')}`).then(r => r.json())
        liveEnv.value = envData
        _prefillFromLiveEnv(envData)
      } catch (e) {
        console.warn('Could not load running env:', e)
      }
    }
  } catch (e) {
    console.warn('Could not load running services:', e)
  }
}

function _prefillFromLiveEnv(envData) {
  const core = envData.traefik || envData.sonarr || envData.radarr || envData.plex || {}
  for (const [envKey, field] of Object.entries(ENV_TO_FIELD)) {
    const val = core[envKey] ?? envData.tailscale?.[envKey] ?? envData.tinyauth?.[envKey] ?? envData.cloudflared?.[envKey] ?? envData.plex?.[envKey]
    if (val !== undefined && val !== '***') {
      const current = req[field]
      const isEmpty = current === '' || current === undefined || current === null || (typeof current === 'number' && current === defaults[field])
      if (isEmpty) {
        if (field === 'puid' || field === 'pgid') {
          const num = parseInt(val, 10)
          if (num) req[field] = num
        } else if (!current) {
          req[field] = val
        }
      }
    }
  }
  const domain = _extractDomain(envData)
  if (domain && !req.domain) req.domain = domain
  const lanSubnet = envData.tinyauth?.TINYAUTH_LAN_SUBNET
  if (lanSubnet && !req.lan_subnet) req.lan_subnet = lanSubnet
}

function _extractDomain(envData) {
  const appurl = envData.tinyauth?.TINYAUTH_APPURL || ''
  const m = appurl.match(/https?:\/\/[^.]+\.([^.]+\.[^\s/]+)/)
  return m ? m[1] : ''
}

function isFieldFromLive(field) {
  if (!liveServices.value.size) return false
  if (field === 'domain') {
    const liveDomain = _extractDomain(liveEnv.value)
    return liveDomain !== '' && req.domain === liveDomain
  }
  if (field === 'lan_subnet') {
    const liveSubnet = liveEnv.value.tinyauth?.TINYAUTH_LAN_SUBNET || ''
    return liveSubnet !== '' && req.lan_subnet === liveSubnet
  }
  if (field === 'puid' || field === 'pgid') {
    const liveVal = _getLiveEnvValue(field)
    return liveVal !== null && parseInt(liveVal, 10) === req[field]
  }
  const val = req[field]
  if (!val || typeof val !== 'string') return false
  return val === _getLiveEnvValue(field)
}

function _getLiveEnvValue(field) {
  for (const [envKey, f] of Object.entries(ENV_TO_FIELD)) {
    if (f === field) {
      for (const name of Object.keys(liveEnv.value)) {
        const v = liveEnv.value[name]?.[envKey]
        if (v && v !== '***') return v
      }
    }
  }
  return null
}

// ── Computed ───────────────────────────────────────────────────────────────
const flatServices = computed(() => {
  const out = []
  for (const [cat, svcs] of Object.entries(rawCatalog.value)) {
    for (const svc of svcs) {
      out.push({
        ...svc,
        category: cat,
        icon: ICONS[svc.key] || '📦',
        short_desc: SHORT_DESCS[svc.key] || svc.description,
      })
    }
  }
  return out
})

// Lookup map: key → service. Avoids repeated .find() calls in helpers.
const svcByKey = computed(() => {
  const map = {}
  for (const svc of flatServices.value) map[svc.key] = svc
  return map
})

const filteredServices = computed(() => {
  const q = search.value.toLowerCase()
  const filtered = flatServices.value.filter(svc => {
    if (activeFilter.value && svc.category !== activeFilter.value) return false
    if (!q) return true
    return (
      svc.display_name.toLowerCase().includes(q) ||
      (svc.short_desc || '').toLowerCase().includes(q) ||
      TAG_LABELS[svc.category]?.toLowerCase().includes(q)
    )
  })
  return [...filtered].sort((a, b) => a.display_name.localeCompare(b.display_name))
})

const tileMinWidth = computed(() => {
  const longest = flatServices.value.reduce((max, svc) => Math.max(max, svc.display_name.length), 0)
  return Math.max(160, longest * 8 + 48)
})

const selectedServices = computed(() =>
  Object.entries(pick).filter(([, on]) => on).map(([k]) => k)
)

const containerUrls = computed(() => {
  const map = {}
  const host = window.location.hostname
  for (const c of containers.value) {
    if (c.web_url) {
      map[c.id] = c.web_url.replace('://0.0.0.0:', `://${host}:`)
    } else {
      map[c.id] = null
    }
  }
  return map
})

const filteredContainers = computed(() => {
  const q = containerSearch.value.toLowerCase().trim()
  return containers.value
    .filter(c => showStoppedContainers.value || c.state === 'running')
    .filter(c => {
      if (!q) return true
      const cleanName = formatContainerName(c.name).toLowerCase()
      return c.name.toLowerCase().includes(q) || cleanName.includes(q) || c.image.toLowerCase().includes(q)
    })
    .sort((a, b) => {
      if (a.state === 'running' && b.state !== 'running') return -1
      if (a.state !== 'running' && b.state === 'running') return 1
      return a.name.localeCompare(b.name)
    })
})

const selectedContainer = computed(() =>
  containers.value.find(c => c.id === selectedContainerId.value) || null
)

// ── Style helpers — consistent: all take category or key via svcByKey ──────
function catColors(cat)    { return CAT_COLORS[cat] || { bg: 'var(--accent-subtle)', border: 'var(--accent-dim)', text: 'var(--accent)' } }
function tagStyle(cat)     { const c = catColors(cat); return { background: c.bg, color: c.text, borderColor: c.border } }
function tileStyle(cat)    { const c = catColors(cat); return { '--tc': c.text, '--tc-bg': c.bg } }
function tileClass(key)   {
  if (pick[key]) return 'tile-selected'
  return ''
}
function svcPillStyle(key) { const c = catColors(svcByKey.value[key]?.category); return { background: c.bg, color: c.text, borderColor: c.border } }
function svcName(key)      { return svcByKey.value[key]?.display_name || key }

function formatContainerName(n) {
  const clean = n.replace(/^\//, '')
  const base = clean.split('.')[0]
  const svc = svcByKey.value[base]
  if (svc?.display_name) return svc.display_name
  return clean
    .replace(/[-_]/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function containerIcon(name) {
  const clean = name.replace(/^\//, '')
  const base = clean.split('.')[0]
  return ICONS[base] || '📦'
}
function shortImage(img) {
  return img.split('/').slice(-2).join('/').split(':')[0]
}
function humanBytes(b) {
  if (!b || b < 1024) return '0B'
  if (b < 1048576) return (b / 1024).toFixed(1) + 'K'
  if (b < 1073741824) return (b / 1048576).toFixed(1) + 'M'
  return (b / 1073741824).toFixed(2) + 'G'
}
function containerUptime(c) {
  if (!c.created) return '—'
  const secs = Math.max(0, Math.floor(Date.now() / 1000) - c.created)
  if (secs < 60) return `${secs}s`
  if (secs < 3600) return `${Math.floor(secs / 60)}m`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`
  return `${Math.floor(secs / 86400)}d`
}
function containerStatusLabel(c) {
  if (c.health === 'unhealthy') return 'Unhealthy'
  if (c.health === 'starting') return 'Starting'
  if (c.state === 'restarting') return 'Restarting'
  if (c.state === 'paused') return 'Paused'
  if (c.state === 'dead') return 'Stopped'
  if (c.state === 'exited') return 'Exited'
  if (c.state === 'running') return 'Running'
  return c.status || 'Unknown'
}
function containerDotClass(c) {
  if (c.health === 'unhealthy' || c.state === 'dead') return 'dot-err'
  if (c.state === 'restarting' || c.health === 'starting' || c.state === 'paused') return 'dot-warn'
  if (c.state === 'running') return 'dot-ok'
  return 'dot-off'
}
function instanceCardState(c) {
  if (c.health === 'unhealthy' || c.state === 'dead') return 'instance-err'
  if (c.state === 'restarting' || c.health === 'starting' || c.state === 'paused') return 'instance-warn'
  if (c.state === 'running') return 'instance-ok'
  return 'instance-off'
}
function containerMetrics(c, verbose = false) {
  const parts = []
  const up = containerUptime(c)
  if (up !== '—') parts.push(`up ${up}`)
  const stat = stats.value[c.id]
  if (stat) {
    if (typeof stat.cpu_percent === 'number') {
      parts.push(`${stat.cpu_percent.toFixed(1)}% CPU`)
    }
    if (typeof stat.mem_usage_bytes === 'number') {
      const memMb = (stat.mem_usage_bytes / 1048576).toFixed(0)
      parts.push(`${memMb}MB RAM`)
    }
    if (verbose) {
      const rx = typeof stat.net_rx_bytes === 'number' ? humanBytes(stat.net_rx_bytes) : '0B'
      const tx = typeof stat.net_tx_bytes === 'number' ? humanBytes(stat.net_tx_bytes) : '0B'
      parts.push(`↓${rx} ↑${tx}`)
    }
  }
  return parts.join(' · ')
}
function containerPorts(c) {
  if (!c.ports || !c.ports.length) return '—'
  const items = c.ports
    .filter(p => p.host_port)
    .map(p => `${p.host_port}:${p.container_port}`)
  return items.length ? items.join(', ') : '—'
}
function createdTime(c) {
  if (!c.created) return 'Unknown'
  return new Date(c.created * 1000).toLocaleString()
}

function openContainer(url) {
  window.open(url, '_blank', 'noopener,noreferrer')
}

function selectContainer(id) {
  selectedContainerId.value = selectedContainerId.value === id ? null : id
  if (selectedContainerId.value) {
    containerLogs.value = ''
    containerLogsName.value = ''
    containerLogsLoading.value = false
  }
}

function clearSelection() {
  selectedContainerId.value = null
  containerLogs.value = ''
  containerLogsName.value = ''
  containerLogsLoading.value = false
}

async function refreshContainers() {
  try {
    containers.value = await fetch('/api/containers').then(r => r.json())
  } catch (e) {
    console.error('Containers refresh failed:', e)
  }
  if (selectedContainerId.value && !containers.value.some(c => c.id === selectedContainerId.value)) {
    clearSelection()
  }
}

function openStatsWebSocket() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  statsWs = new WebSocket(`${proto}//${window.location.host}/ws/stats`)
  statsWs.onmessage = e => {
    const msg = JSON.parse(e.data)
    if (msg.type === 'stats') {
      const next = {}
      for (const row of msg.containers) next[row.id] = row
      stats.value = next
    }
  }
  statsWs.onclose = () => { if (statsWsActive) setTimeout(openStatsWebSocket, 2000) }
}

async function containerAction(name, kind) {
  try {
    const r = await fetch(`/api/containers/${name}/${kind}`, { method: kind === 'remove' ? 'DELETE' : 'POST' })
    if (r.ok) {
      showToast(`${kind} ${name} → ok`)
      await new Promise(res => setTimeout(res, 500))
      await refreshContainers()
    } else {
      showToast(`${kind} ${name} failed: ${await r.text()}`, 'err')
    }
  } catch (e) {
    showToast(`${kind} ${name}: ${e.message}`, 'err')
  }
}

async function removeContainer(name) {
  const c = containers.value.find(x => x.name === name)
  try {
    if (c?.state === 'running') {
      showToast(`Stopping ${name}…`, 'warn', 2000)
      const s = await fetch(`/api/containers/${name}/stop`, { method: 'POST' })
      if (!s.ok) {
        showToast(`Could not stop ${name}`, 'err')
        return
      }
      await new Promise(res => setTimeout(res, 800))
    }
    const r = await fetch(`/api/containers/${name}`, { method: 'DELETE' })
    if (r.ok) {
      showToast(`${name} removed`)
      await refreshContainers()
      if (selectedContainerId.value && !containers.value.some(c => c.name === name)) {
        clearSelection()
      }
    } else {
      showToast(`Remove failed: ${await r.text()}`, 'err')
    }
  } catch (e) {
    showToast(`Remove error: ${e.message}`, 'err')
  }
}

async function loadLogs(name) {
  const container = containers.value.find(c => c.name === name)
  if (!container) {
    showToast(`No container named ${name}`, 'warn')
    return
  }
  if (selectedContainerId.value !== container.id) {
    selectContainer(container.id)
  }
  containerLogsName.value = name
  containerLogsLoading.value = true
  containerLogs.value = ''
  try {
    const r = await fetch(`/api/containers/${name}/logs?tail=300`, { method: 'POST' })
    containerLogs.value = await r.text()
  } catch (e) {
    containerLogs.value = String(e)
    showToast(`Log fetch error: ${e.message}`, 'err')
  } finally {
    containerLogsLoading.value = false
  }
}

function confirmRemove(name) {
  if (window.confirm(`Remove ${name}? This stops and deletes the container.`)) {
    removeContainer(name)
  }
}

// ── Actions ────────────────────────────────────────────────────────────────
// Map service key → config section id (only services that have a config section)
const SERVICE_SECTION = { cloudflared: 'cloudflare', traefik: 'cloudflare', tailscale: 'tailscale', tinyauth: 'tinyauth', plex: 'plex' }

function toggle(key) {
  pick[key] = !pick[key]
  previewText.value = ''
  previewWarnings.value = []
  const section = SERVICE_SECTION[key]
  if (section) {
    expanded[section] = pick[key]
  }
}

// camelCase throughout — was mixed snake_case/camelCase previously
function toggleCfg(id) {
  expanded[id] = !expanded[id]
}

// ── Tinyauth credential generators ────────────────────────────────────────
const generatedPassword = ref('')

async function generateCredentials() {
  // Random 16-char password: letters + digits, no ambiguous chars
  const chars = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789'
  const arr = new Uint8Array(16)
  crypto.getRandomValues(arr)
  const password = Array.from(arr).map(b => chars[b % chars.length]).join('')
  try {
    const r = await fetch('/api/utils/hash-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    })
    if (!r.ok) throw new Error(await r.text())
    const { hash } = await r.json()
    req.tinyauth_users = `admin:${hash}`
    generatedPassword.value = password
    showToast('Credentials generated — save the password shown below', 'warn', 8000)
  } catch (e) {
    showToast(`Generate failed: ${e.message}`, 'err')
  }
}

async function parseAndAdd() {
  const content = addInput.value.trim()
  if (!content) { showToast('Enter a URL or image name first', 'warn'); return }

  addParsing.value = true
  addResult.value  = null
  try {
    const r = await fetch('/api/custom-app/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: addTab.value, content }),
    })
    if (!r.ok) {
      const msg = await r.text()
      showToast(msg, 'err', 6000)
      return
    }
    addResult.value = await r.json()
    showToast(`Parsed — ${addResult.value.services.length} service(s) found`)
  } catch (e) {
    showToast(`Parse failed: ${e.message}`, 'err')
  } finally {
    addParsing.value = false
  }
}

function confirmCustomApp() {
  customYaml.value = addResult.value?.yaml || ''
  showToast('Custom app added to stack — click Deploy to apply')
}

function readFile(file) {
  addFileName.value = file.name
  const reader = new FileReader()
  reader.onload = () => {
    addInput.value = reader.result
    addTab.value = 'compose'
    showToast(`Loaded ${file.name} — click Parse & add`)
  }
  reader.onerror = () => showToast('Failed to read file', 'err')
  reader.readAsText(file)
}

function onFilePick(e) {
  const file = e.target.files?.[0]
  if (file) readFile(file)
  e.target.value = ''
}

function onFileDrop(e) {
  const file = e.dataTransfer?.files?.[0]
  if (file && /\.(ya?ml)$/i.test(file.name)) {
    readFile(file)
  } else {
    showToast('Only .yml / .yaml files are supported', 'warn')
  }
}

// ── Port conflict check ───────────────────────────────────────────────────────
let _portCheckTimer = null
function schedulePortCheck() {
  clearTimeout(_portCheckTimer)
  _portCheckTimer = setTimeout(checkPorts, 600)
}

async function checkPorts() {
  if (!selectedServices.value.length) { portConflicts.value = []; return }
  portsChecking.value = true
  try {
    const r = await fetch('/api/stack/port-check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildRequest()),
    })
    if (r.ok) {
      const data = await r.json()
      portConflicts.value = data.conflicts || []
    }
  } catch (e) {
    console.warn('Port check failed:', e)
  } finally {
    portsChecking.value = false
  }
}

function acceptPortSuggestion(conflict) {
  portOverrides[conflict.service] = conflict.suggested_port
  // Remove this conflict from the list optimistically
  portConflicts.value = portConflicts.value.filter(c => c.service !== conflict.service)
  // Re-check with the new override applied
  schedulePortCheck()
  showToast(`Port changed: ${conflict.service} → ${conflict.suggested_port}`)
}

// ── API ────────────────────────────────────────────────────────────────────
async function loadCatalog() {
  try {
    rawCatalog.value = await fetch('/api/catalog').then(r => r.json())
  } catch (e) {
    showToast('Failed to load catalog — check the backend is running', 'err')
  }
}

function buildRequest() {
  const envForService = (key) => {
    const rows = (extraEnvRows[key] || []).filter(r => r.k && r.k.trim())
    if (!rows.length) return {}
    const obj = {}
    for (const r of rows) obj[r.k.trim()] = r.v ?? ''
    return obj
  }

  return {
    domain:                    req.domain,
    timezone:                  req.timezone,
    puid:                      req.puid,
    pgid:                      req.pgid,
    config_root:               req.config_root,
    media_root:                req.media_root,
    cloudflare_token:          req.cloudflare_token || undefined,
    cloudflare_tunnel_token:   req.cloudflare_tunnel_token || undefined,
    plex_claim:                req.plex_claim || undefined,
    plex_server_name:          req.plex_server_name,
    plex_url:                  req.plex_url || req.external_plex_url || undefined,
    plex_token:                req.plex_token || undefined,
    external_plex_url:         req.external_plex_url || undefined,
    tailscale_auth_key:        req.tailscale_auth_key,
    tailscale_routes:          req.tailscale_routes,
    tailscale_hostname:        req.tailscale_hostname,
    tinyauth_enabled:          !!pick['tinyauth'],
    tinyauth_users:            req.tinyauth_users,
    tinyauth_app_url:          req.tinyauth_app_url,
    lan_subnet:                req.lan_subnet,
    services:                  selectedServices.value.map(k => ({
      key: k, enabled: true,
      port_override: portOverrides[k] || undefined,
      extra_env:     envForService(k),
    })),
    custom_yaml:               customYaml.value || undefined,
  }
}

const previewWarnings = ref([])

async function preview() {
  previewLoading.value = true
  previewText.value = ''
  previewWarnings.value = []
  expanded.deploy = true
  try {
    const r = await fetch('/api/stack/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildRequest()),
    })
    if (!r.ok) throw new Error(await r.text())
    const data = await r.json()
    previewText.value = data.yaml
    previewWarnings.value = data.warnings || []
    const warnCount = previewWarnings.value.length
    showToast(`Generated — ${data.bytes} bytes${warnCount ? ` · ${warnCount} warning(s)` : ''}`)
  } catch (e) {
    const msg = typeof e === 'object' && e.errors
      ? e.errors.map(x => x.message).join(' | ')
      : e.message || String(e)
    showToast(`Generate failed: ${msg}`, 'err', 8000)
  } finally {
    previewLoading.value = false
  }
}

async function purgeAndRetry() {
  const names = deployConflicts.value
  if (!names.length) return
  deploying.value = true
  deployOutput.value = ''
  try {
    const r = await fetch('/api/stack/purge-conflicts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names }),
    })
    const data = await r.json()
    if (data.errors?.length) {
      showToast(`Purge errors: ${data.errors.join('; ')}`, 'err', 7000)
      deploying.value = false
      return
    }
    showToast(`Removed: ${data.removed.join(', ')} — redeploying…`, 'ok', 4000)
    deployConflicts.value = []
    deploying.value = false
    await deploy()
  } catch (e) {
    showToast(`Purge failed: ${e.message}`, 'err')
    deploying.value = false
  }
}

async function deploy() {
  deploying.value = true
  deployOutput.value = ''
  previewText.value = ''
  previewWarnings.value = []
  expanded.deploy = true
  try {
    const r = await fetch('/api/stack/deploy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildRequest()),
    })
    const data = await r.json()
    if (!r.ok) {
      deployOk.value = false
      const validationErrors = (data.errors || [])
      const lines = validationErrors.map(e => {
        const prefix = e.service ? `[${e.service}]` : ''
        return `✗ ${prefix} ${e.message || e}`
      })
      const detail = data.detail || data.message || ''
      deployOutput.value = lines.length
        ? lines.join('\n')
        : detail || `HTTP ${r.status}`
      showToast(lines.length ? lines[0] : (detail || 'Deploy failed'), 'err', 7000)
      return
    }
    deployOk.value = data.ok
    deployConflicts.value = data.conflicts || []
    deployOutput.value = [data.stdout, data.stderr ? '--- stderr ---\n' + data.stderr : '']
      .filter(Boolean).join('\n').trim()
    if (data.ok) {
      showToast('Deploy complete', 'ok', 5000)
      // Clear selections — deployed stack is now running; live dots show status
      Object.keys(pick).forEach(k => { pick[k] = false })
    } else if (deployConflicts.value.length) {
      showToast(`${deployConflicts.value.length} container conflict(s) — click "Remove conflicts & retry"`, 'warn', 8000)
    } else {
      showToast('Deploy failed — see output below', 'err', 5000)
    }
  } catch (e) {
    deployOk.value = false
    deployOutput.value = String(e)
    showToast(`Deploy error: ${e.message}`, 'err')
  } finally {
    deploying.value = false
  }
}

// Auto-expand the config section when a service with one is first selected
const SERVICE_CFG = { cloudflared: 'cloudflare', traefik: 'cloudflare', tailscale: 'tailscale', tinyauth: 'tinyauth', plex: 'plex' }
watch(() => ({ ...pick }), (cur, prev) => {
  for (const [svcKey, cfgId] of Object.entries(SERVICE_CFG)) {
    if (cur[svcKey] && !prev?.[svcKey]) expanded[cfgId] = true
  }
})

watch(addInput, () => { addResult.value = null })
watch(addTab,   () => { addResult.value = null; addInput.value = ''; addFileName.value = '' })
watch(selectedServices, schedulePortCheck)

let runningPollTimer = null

onMounted(() => {
  localStorage.removeItem('rad-stack-builder-pick')
  loadCatalog()
  loadRunningServices()
  runningPollTimer = setInterval(loadRunningServices, 15000)
  refreshContainers()
  containersPollTimer = setInterval(refreshContainers, 10000)
  statsWsActive = true
  openStatsWebSocket()
})

onUnmounted(() => {
  if (runningPollTimer) clearInterval(runningPollTimer)
  if (containersPollTimer) clearInterval(containersPollTimer)
  statsWsActive = false
  if (statsWs) statsWs.close()
})
</script>

<style scoped>
/* ── Layout ─────────────────────────────────────────────────────────────── */
.builder { padding-bottom: 80px; }

.builder-layout {
  display: flex;
  flex-direction: row;
  gap: 24px;
  align-items: flex-start;
}
.config-panel {
  flex: 0 0 280px;
  min-width: 0;
}
.grid-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

@media (max-width: 960px) {
  .builder-layout { flex-direction: column; }
  .config-panel { flex: none; width: 100%; }
  .tile-header, .instances-header { flex-direction: column; align-items: stretch; }
  .instances-controls { flex-wrap: wrap; }
  .tile-search, .instances-search { flex: 1 1 100%; max-width: none; }
}

/* ── Header ─────────────────────────────────────────────────────────────── */
.builder-header { margin-bottom: var(--space-1); display: flex; align-items: flex-end; justify-content: space-between; gap: var(--space-2); }
.header-actions { display: flex; align-items: center; gap: 8px; }
.header-sub     { font-size: 12px; color: var(--fg-2); margin-top: 2px; display: flex; align-items: center; gap: 5px; }
.header-sub-sep { opacity: 0.5; }
.btn-review     { font-size: 13px; font-weight: 600; font-family: var(--font-sans); padding: 6px 12px; border-radius: var(--radius); border: 1.5px solid var(--accent); background: transparent; color: var(--accent); cursor: pointer; transition: background 0.13s; }
.btn-review:hover:not(:disabled) { background: var(--accent-subtle); }
.btn-review:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Filter row ─────────────────────────────────────────────────────────── */
.search-wrap { position: relative; flex: 1; min-width: 140px; }
.search-icon { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); font-size: 13px; }
.search-input {
  width: 100%;
  padding: 7px 10px 7px 30px;
  font-family: var(--font-sans);
  font-size: 13px;
  background: var(--bg-0);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg-0);
  box-sizing: border-box;
}
.search-input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }

/* ── Cards ──────────────────────────────────────────────────────────────── */
.card {
  background: var(--bg-1);
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.tile-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}
.tile-card .service-grid { margin-top: var(--space-1); }
.tile-title {
  font-size: 12.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-2);
  margin: 0 0 4px;
}
.tile-search { max-width: 240px; flex: 0 0 220px; }

.instances-card { gap: var(--space-2); }
.instances-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}
.instances-title {
  font-size: 12.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-2);
  margin: 0 0 4px;
}
.instances-controls {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.instances-search { max-width: 220px; flex: 0 0 200px; }
.instances-search .search-input { padding-top: 4px; padding-bottom: 4px; font-size: 12px; }
.instances-search .search-icon { font-size: 11px; }
.toggle-stopped {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--fg-2);
  white-space: nowrap;
}
.toggle-stopped input { cursor: pointer; }

.instances-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 6px;
}
.instance-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 5px 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-0);
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s;
}
.instance-card:hover { background: var(--bg-1); border-color: var(--border-strong); }
.instance-card.selected {
  box-shadow: var(--shadow-1);
  border-color: var(--accent);
}
.instance-card.instance-ok { border-color: rgba(22,163,74,0.25); background: rgba(22,163,74,0.05); }
.instance-card.instance-warn { border-color: rgba(217,119,6,0.25); background: rgba(217,119,6,0.05); }
.instance-card.instance-err { border-color: rgba(220,38,38,0.35); background: rgba(220,38,38,0.06); }
.instance-card.instance-off { border-color: var(--border); }
.instance-top {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  min-width: 0;
}
.instance-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  font-size: 9px;
  flex: 0 0 8px;
}
.instance-icon {
  font-size: 15px;
  flex-shrink: 0;
}
.instance-icon.link { color: var(--purple); }
.instance-name {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--fg-0);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: none;
  border: none;
  padding: 0;
  text-align: left;
  cursor: default;
  font-family: inherit;
  line-height: 1.1;
  text-transform: uppercase;
  appearance: none;
}
.instance-name.has-link {
  cursor: pointer;
  color: var(--purple);
  border: none;
  background: none;
}
.instance-name.has-link:hover { text-decoration: underline; }
.instance-name.has-link:focus { outline: none; text-decoration: underline; }
.instance-bottom {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 0;
  min-width: 0;
  padding-left: 14px;
}
.instance-actions {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 1px;
  flex: 0 0 auto;
}
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border-radius: 5px;
  border: 1.5px solid var(--border);
  background: var(--bg-1);
  color: var(--fg-1);
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
  transition: all 0.12s;
}
.icon-btn:hover { border-color: var(--border-strong); background: var(--bg-2); color: var(--fg-0); }
.icon-btn.danger { border-color: var(--err-dim); color: var(--err); }
.icon-btn.danger:hover { background: var(--err); color: #fff; }

.instances-empty {
  font-size: 11.5px;
  color: var(--fg-2);
  padding: 12px;
  text-align: center;
  grid-column: 1 / -1;
}

.instance-detail {
  border-top: 1px solid var(--border);
  padding-top: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}
.detail-name {
  font-size: 13px;
  font-weight: 600;
}
.detail-meta {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 8px;
  font-size: 12px;
  color: var(--fg-1);
  align-items: baseline;
}
.detail-status {
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 11px;
  color: var(--fg-2);
}
.detail-metrics {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: var(--space-2);
}
.detail-label {
  display: block;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-2);
  margin-bottom: 4px;
}
.detail-value {
  font-size: 12px;
  color: var(--fg-0);
}
.detail-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}
.detail-actions .icon-btn { flex: 0 0 auto; }
.detail-logs {
  max-height: 220px;
  overflow: auto;
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: var(--space-2);
  font-size: 11.5px;
}
.detail-logs.muted {
  color: var(--fg-2);
  font-style: italic;
}

/* ── Service grid ───────────────────────────────────────────────────────── */
/* ── Service grid — compact fixed-column layout ──────────────────────────── */
.service-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(var(--tile-min-width, 180px), 1fr));
  gap: 4px;
  margin-bottom: var(--space-2);
}

/* Single-line tile: icon · name · live dot */
.tile {
  --tc:    var(--accent);
  --tc-bg: var(--accent-subtle);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 9px;
  background: var(--bg-0);
  border: 1.5px solid transparent;
  border-radius: var(--radius-sm);
  text-align: left;
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s;
  font-family: var(--font-sans);
  min-width: 0;
}
.tile:hover { background: var(--bg-2); border-color: var(--border); }
.tile.on,
.tile-selected    { background: var(--accent-subtle); border-color: var(--accent); }

.tile-icon  { font-size: 13px; line-height: 1; flex-shrink: 0; }
.tile-name  {
  font-size: 12.5px; font-weight: 600; color: var(--fg-0);
  letter-spacing: -0.01em; flex: 1; min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.tile.on .tile-name,
.tile-selected .tile-name { color: var(--accent); }
.tile-status { display: flex; align-items: center; justify-content: flex-end; flex: 0 0 auto; margin-left: auto; }
.tile-dot { font-size: 11px; flex-shrink: 0; line-height: 1; }
.dot-ok  { color: #16a34a; text-shadow: 0 0 6px rgba(22,163,74,0.9), 0 0 12px rgba(22,163,74,0.5); }
.dot-warn { color: var(--warn); text-shadow: 0 0 6px rgba(217,119,6,0.5); }
.dot-err { color: #dc2626; text-shadow: 0 0 6px rgba(220,38,38,0.9), 0 0 12px rgba(220,38,38,0.5); }
.dot-off { color: var(--fg-2); opacity: 0.6; }



/* ── Config area ────────────────────────────────────────────────────────── */
.config-area    { display: flex; flex-direction: column; gap: 6px; }
/* CfgSection — styles for the inline component template */
.cfg-section      { background: var(--bg-1); border: 1.5px solid var(--border); border-radius: var(--radius); overflow: hidden; transition: box-shadow 0.13s; }
.cfg-section.open { box-shadow: var(--shadow-1); }
.cfg-head         { display: flex; align-items: center; gap: 8px; padding: 6px 12px; user-select: none; }
.cfg-head:hover   { background: var(--bg-2); }
.cfg-icon         { font-size: 13px; }
.cfg-title        { font-size: 12.5px; font-weight: 600; color: var(--fg-0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; flex: 1; }
/* cfg-badge removed */
.cfg-badge-mode   { font-size: 9px; font-weight: 600; color: var(--fg-2); background: var(--bg-2); padding: 1px 6px; border-radius: 20px; border: 1px solid var(--border); white-space: nowrap; flex-shrink: 0; }
.cfg-head-pinned  { cursor: default; }
.cfg-head-pinned:hover { background: var(--bg-1); }
.cfg-chevron      { display: none; }


.cfg-body         { padding: 2px 12px 8px; border-top: 1px solid var(--border); }
.cfg-body input   { padding: 2px 6px; font-size: 10px; }
input.cfg-readonly { background: var(--bg-2); color: var(--fg-2); opacity: 0.7; cursor: default; border-style: dashed; }

.cfg-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-top: 6px; }
.cfg-field        { display: flex; flex-direction: column; gap: 1px; min-width: 0; overflow: hidden; }
.cfg-field.span2  { grid-column: span 2; }
.cfg-field .cfg-label:empty, .cfg-label:only-child:empty { visibility: hidden; }
.cfg-label        { font-size: 9.5px; font-weight: 600; color: var(--fg-1); display: flex; align-items: center; gap: 6px; justify-content: space-between; min-width: 0; width: 100%; }
.cfg-link         { font-size: 11px; color: var(--accent); margin-left: auto; text-decoration: none; }
.cfg-link:hover   { text-decoration: underline; }

/* Generate buttons inside label rows */
.gen-btn {
  font-size: 10px; font-weight: 600; font-family: var(--font-sans);
  padding: 1px 8px; border-radius: 20px; cursor: pointer;
  background: var(--accent-subtle); color: var(--accent);
  border: 1px solid var(--accent-dim); transition: all 0.13s;
  flex-shrink: 0; white-space: nowrap;
}
.gen-btn:hover { background: var(--accent); color: #fff; }

/* Generated password reveal box */
.generated-password-box {
  grid-column: span 2;
  padding: 7px 10px; border-radius: 6px;
  background: var(--warn-bg); border: 1.5px solid rgba(217,119,6,0.3);
  min-width: 0; overflow: hidden;
}
.gen-pw-label  { display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--warn); font-weight: 600; margin-bottom: 4px; }
.gen-pw-value  { display: block; font-family: var(--font-mono); font-size: 12px; color: var(--fg-0); background: var(--bg-1); padding: 4px 8px; border-radius: 4px; border: 1px solid var(--border); word-break: break-all; width: 100%; box-sizing: border-box; }
.gen-pw-dismiss { font-size: 10px; color: var(--fg-2); background: none; border: none; cursor: pointer; }
.gen-pw-dismiss:hover { color: var(--fg-0); }
.cfg-hint         { font-size: 9px; color: var(--fg-2); line-height: 1.25; font-style: italic; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cfg-hint code    { font-family: var(--font-mono); font-size: 9.5px; background: var(--bg-2); padding: 1px 4px; border-radius: 3px; }

.cfg-note          { font-size: 10.5px; border-radius: 5px; padding: 4px 9px; line-height: 1.35; margin-top: 5px; }
.cfg-note-purple   { background: var(--accent-subtle); color: var(--fg-1); border: 1px solid var(--accent-dim); }
.cfg-note-pink     { background: rgba(219,39,119,0.05); color: var(--fg-1); border: 1px solid rgba(219,39,119,0.15); }
.cfg-note-neutral  { background: var(--bg-0); color: var(--fg-1); border: 1px solid var(--border); }

/* Plex mode toggle */
.mode-toggle { display: flex; background: var(--bg-0); border-radius: 6px; padding: 2px; gap: 2px; margin-top: 5px; }
.mode-btn    { flex: 1; padding: 3px 8px; border-radius: 4px; font-family: var(--font-sans); font-size: 11.5px; font-weight: 500; border: none; background: transparent; color: var(--fg-2); cursor: pointer; transition: all 0.13s; }
.mode-btn.active { background: var(--bg-1); color: var(--fg-0); box-shadow: var(--shadow-1); }

/* TOTP toggle */
.toggle-field  { flex-direction: column; gap: var(--space-2); }
.toggle        { display: flex; align-items: center; gap: var(--space-2); cursor: pointer; user-select: none; }
.toggle input  { display: none; }
.toggle-track  { width: 34px; height: 19px; border-radius: 10px; background: var(--border-strong); position: relative; flex-shrink: 0; transition: background 0.15s; }
.toggle-track::after { content: ''; position: absolute; top: 2.5px; left: 2.5px; width: 14px; height: 14px; border-radius: 50%; background: #fff; transition: transform 0.15s; }
.toggle input:checked ~ .toggle-track            { background: var(--accent); }
.toggle input:checked ~ .toggle-track::after     { transform: translateX(15px); }
.toggle-label  { font-size: 12px; color: var(--fg-1); }

/* Custom app section */
.tab-row       { display: flex; background: var(--bg-0); border-radius: 7px; padding: 3px; gap: 2px; margin-top: 10px; margin-bottom: 12px; }
.tab-btn       { flex: 1; padding: 5px 8px; border-radius: 5px; border: none; font-family: var(--font-sans); font-size: 12px; font-weight: 500; cursor: pointer; background: transparent; color: var(--fg-2); transition: all 0.13s; }
.tab-btn.active { background: var(--bg-1); color: var(--fg-0); box-shadow: var(--shadow-1); }
.custom-hint   { margin: 0 0 8px; }
.custom-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
.compose-textarea { font-family: var(--font-mono); font-size: 11.5px; width: 100%; height: 160px; resize: vertical; background: #0e0f14; color: #e8eaf5; border: 1.5px solid #252a3d; border-radius: 7px; padding: 10px 12px; outline: none; box-sizing: border-box; line-height: 1.6; }
.url-input     { font-family: var(--font-mono); font-size: 12px; width: 100%; background: var(--bg-1); border: 1.5px solid var(--border); border-radius: 6px; padding: 8px 10px; outline: none; color: var(--fg-0); }
.file-drop     { border: 2px dashed var(--border); border-radius: 9px; padding: 28px 20px; text-align: center; background: var(--bg-0); cursor: pointer; margin-top: 8px; }
.file-drop-icon  { font-size: 26px; margin-bottom: 6px; }
.file-drop-title { font-size: 13.5px; font-weight: 600; color: var(--fg-0); margin-bottom: 3px; }
.file-drop-sub   { font-size: 12px; color: var(--fg-2); }
.file-drop-name  { font-size: 11px; color: var(--ok); font-weight: 600; margin-top: 4px; }

/* Parse result preview */
.parse-result {
  margin-top: 12px;
  border: 1.5px solid var(--ok);
  border-radius: 7px;
  overflow: hidden;
  background: var(--ok-bg);
}
.parse-result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 12px;
  background: var(--ok-bg);
  border-bottom: 1px solid rgba(22,163,74,0.15);
}
.parse-result-title { font-size: 12px; font-weight: 600; color: var(--ok); }
.parse-confirm {
  font-size: 11.5px; font-weight: 600; font-family: var(--font-sans);
  padding: 3px 10px; border-radius: 5px;
  background: var(--ok); color: #fff; border: none; cursor: pointer;
}
.parse-svc {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 5px 12px; border-top: 1px solid rgba(22,163,74,0.1);
  font-size: 11.5px;
}
.parse-svc-name  { font-weight: 700; color: var(--fg-0); }
.parse-svc-image { font-family: var(--font-mono); font-size: 10.5px; color: var(--fg-2); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.parse-svc-port  { font-family: var(--font-mono); font-size: 9.5px; background: var(--bg-2); border: 1px solid var(--border); border-radius: 4px; padding: 1px 5px; color: var(--fg-2); }
.parse-confirmed { padding: 5px 12px; font-size: 11px; font-weight: 600; color: var(--ok); border-top: 1px solid rgba(22,163,74,0.15); }

/* Deploy area */

.deploy-output-area { margin-top: var(--space-4); max-width: 100%; }
.deploy-btn    { font-size: 11.5px; padding: 4px 10px; white-space: nowrap; }
.output        { max-height: 380px; overflow: auto; background: var(--bg-0); padding: var(--space-3); border-radius: var(--radius); font-size: 12px; line-height: 1.4; white-space: pre-wrap; word-break: break-word; border: 1px solid var(--border); margin: 0; }
.output-block  { border-radius: var(--radius); overflow: hidden; margin-top: var(--space-2); }
.output-label  { padding: 6px 12px; font-size: 12px; font-weight: 600; }
.output-block.ok  .output-label { background: var(--ok-bg);  color: var(--ok);  }
.output-block.err .output-label { background: var(--err-bg); color: var(--err); }
.output-block .output { border-top: none; border-radius: 0; }

.preview-warnings {
  border: 1.5px solid rgba(217,119,6,0.4);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--warn-bg);
  margin-bottom: var(--space-2);
}
.preview-warn-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid rgba(217,119,6,0.12);
}
.preview-warn-row:last-child { border-bottom: none; }
.preview-warn-icon { color: var(--warn); font-size: 13px; flex-shrink: 0; }
.preview-warn-svc {
  font-size: 11.5px; font-weight: 600; font-family: var(--font-mono);
  color: var(--fg-0); background: var(--bg-1);
  border: 1px solid var(--border); border-radius: 4px;
  padding: 1px 6px; white-space: nowrap;
}
.preview-warn-msg { font-size: 12px; color: var(--fg-1); }

/* Port conflict banner (service grid) */
.port-conflict-banner {
  margin-top: var(--space-3);
  border: 1.5px solid rgba(217,119,6,0.4);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--warn-bg);
}
.port-conflict-banner-head {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(217,119,6,0.15);
}
.port-conflict-icon { font-size: 14px; color: var(--warn); }
.port-conflict-title { font-size: 12px; font-weight: 600; color: var(--warn); }
.port-conflict-checking { font-size: 11px; color: var(--fg-2); font-style: italic; }
.port-conflict-row {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 12px;
}
.port-conflict-svc {
  font-size: 12px; font-weight: 600; color: var(--fg-0); min-width: 90px;
}
.port-conflict-detail {
  font-size: 12px; color: var(--fg-1); flex: 1;
}
.port-conflict-detail code {
  font-family: var(--font-mono); font-size: 11.5px;
  background: var(--bg-1); border: 1px solid var(--border);
  border-radius: 4px; padding: 1px 5px; color: var(--fg-0);
}
.port-conflict-accept {
  font-size: 11px; font-weight: 600; font-family: var(--font-sans);
  padding: 4px 10px; border-radius: 6px;
  border: 1.5px solid var(--accent); background: transparent;
  color: var(--accent); cursor: pointer; white-space: nowrap;
  transition: all 0.13s; margin-left: auto;
}
.port-conflict-accept:hover { background: var(--accent-subtle); }

/* Container name conflict banner (deploy-time) */
.conflict-banner {
  margin-top: var(--space-3);
  border: 1.5px solid rgba(217,119,6,0.4);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--warn-bg);
}
.conflict-banner-head {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(217,119,6,0.15);
}
.conflict-icon  { font-size: 14px; color: var(--warn); }
.conflict-title { font-size: 12px; font-weight: 600; color: var(--warn); }
.conflict-names {
  display: flex; flex-wrap: wrap; gap: 5px;
  padding: 8px 12px;
}
.conflict-name {
  font-family: var(--font-mono); font-size: 11.5px;
  background: var(--bg-1); border: 1px solid var(--border);
  border-radius: 4px; padding: 2px 7px; color: var(--fg-0);
}
.conflict-actions {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; flex-wrap: wrap;
  padding: 8px 12px;
  border-top: 1px solid rgba(217,119,6,0.15);
}
.conflict-warn { font-size: 11.5px; color: var(--warn); font-weight: 500; }
.conflict-btn {
  font-size: 12px; font-weight: 700; font-family: var(--font-sans);
  padding: 5px 14px; border-radius: 6px; border: none; cursor: pointer;
  background: var(--warn); color: #fff; transition: opacity 0.13s;
  white-space: nowrap;
}
.conflict-btn:disabled { opacity: 0.6; cursor: default; }

/* ── Sticky bottom bar ──────────────────────────────────────────────────── */



.pill-remove   { cursor: pointer; opacity: 0.5; font-size: 9px; margin-left: 1px; }
.pill-remove:hover { opacity: 1; }

.ml-auto       { margin-left: auto; }

/* ── Extra env vars ──────────────────────────────────────────────────────── */
.extraenv-service { border-top: 1px solid var(--border); padding-top: 6px; margin-top: 6px; }
.extraenv-service:first-child { border-top: none; margin-top: 0; }
.extraenv-service-head { display: flex; align-items: center; gap: 7px; cursor: pointer; padding: 3px 2px; border-radius: 5px; user-select: none; }
.extraenv-service-head:hover { background: var(--bg-0); }
.extraenv-icon  { font-size: 12px; }
.extraenv-name  { font-size: 12px; font-weight: 600; color: var(--fg-0); flex: 1; }
.extraenv-count { font-size: 9.5px; font-weight: 700; color: var(--accent); background: var(--accent-subtle); border: 1px solid var(--accent-dim); padding: 1px 6px; border-radius: 20px; }
.extraenv-chevron { font-size: 13px; color: var(--fg-2); transition: transform 0.13s; display: inline-block; }
.extraenv-chevron.open { transform: rotate(90deg); }
.extraenv-rows { margin-top: 6px; display: flex; flex-direction: column; gap: 5px; }
.extraenv-row  { display: flex; align-items: center; gap: 5px; }
.extraenv-key  { font-family: var(--font-mono); font-size: 11.5px; flex: 0 0 160px; padding: 4px 7px; border: 1.5px solid var(--border); border-radius: 5px; background: var(--bg-0); color: var(--fg-0); outline: none; }
.extraenv-key:focus { border-color: var(--accent); }
.extraenv-eq   { font-family: var(--font-mono); font-size: 12px; color: var(--fg-2); flex-shrink: 0; }
.extraenv-val  { font-family: var(--font-mono); font-size: 11.5px; flex: 1; padding: 4px 7px; border: 1.5px solid var(--border); border-radius: 5px; background: var(--bg-0); color: var(--fg-0); outline: none; min-width: 0; }
.extraenv-val:focus { border-color: var(--accent); }
.extraenv-rm   { font-size: 10px; color: var(--fg-2); background: none; border: none; cursor: pointer; padding: 0 3px; flex-shrink: 0; }
.extraenv-rm:hover { color: var(--err); }
.extraenv-add  { font-size: 11.5px; font-weight: 600; font-family: var(--font-sans); color: var(--accent); background: none; border: 1.5px dashed var(--accent-dim); border-radius: 5px; padding: 3px 10px; cursor: pointer; margin-top: 2px; transition: all 0.13s; }
.extraenv-add:hover { background: var(--accent-subtle); }

/* ── Narrow screens: stack vertically ───────────────────────────────────── */
@media (max-width: 767px) {
  .builder-layout {
    flex-direction: column;
  }
  .config-panel {
    flex: 1;
    width: 100%;
  }
  .service-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
}

/* ── Medium screens: 3-column grid ─────────────────────────────────────── */
@media (min-width: 768px) and (max-width: 1079px) {
  .service-grid {
    grid-template-columns: repeat(3, 1fr);
  }
  
}

/* ── Wide screens: always side-by-side, hide bottom bar ────────────────── */
@media (min-width: 1080px) {
  
}
</style>
