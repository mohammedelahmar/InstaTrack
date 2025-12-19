const scriptElement = document.currentScript;
const configElement = document.getElementById("dashboard-config");

let dailyData = [];
let autoRefreshSeconds = 0;
let relationshipsData = {};
let defaultAccount = "";
let aiEnabled = false;
let dashboardConfig = null;

if (configElement && configElement.textContent) {
	try {
		dashboardConfig = JSON.parse(configElement.textContent);
	} catch (error) {
		console.error("Unable to parse dashboard config", error);
	}
}

const getConfigValue = (key, fallback) => {
	if (dashboardConfig && Object.prototype.hasOwnProperty.call(dashboardConfig, key)) {
		return dashboardConfig[key];
	}
	return fallback;
};

dailyData = getConfigValue("daily", []);
autoRefreshSeconds = Number(getConfigValue("auto_refresh_seconds", 0)) || 0;
relationshipsData = getConfigValue("relationships", {});
defaultAccount = getConfigValue("default_account", "") || "";
aiEnabled = Boolean(getConfigValue("ai_enabled", 0));

if (!dashboardConfig && scriptElement) {
	const dataAttribute = scriptElement.dataset.daily;
	if (dataAttribute) {
		try {
			dailyData = JSON.parse(dataAttribute);
		} catch (error) {
			console.error("Unable to parse daily data", error);
		}
	}
	const autoRefreshAttribute = scriptElement.dataset.autoRefresh;
	if (autoRefreshAttribute) {
		const parsed = Number(autoRefreshAttribute);
		if (!Number.isNaN(parsed)) {
			autoRefreshSeconds = parsed;
		}
	}
	const relationshipsAttribute = scriptElement.dataset.relationships;
	if (relationshipsAttribute) {
		try {
			relationshipsData = JSON.parse(relationshipsAttribute);
		} catch (error) {
			console.error("Unable to parse relationships data", error);
		}
	}
	defaultAccount = scriptElement.dataset.defaultAccount || defaultAccount;
	aiEnabled = scriptElement.dataset.aiEnabled === "1" ? true : aiEnabled;
}

if (typeof relationshipsData !== "object" || relationshipsData === null) {
	relationshipsData = {};
}

if (!Array.isArray(dailyData)) {
	dailyData = [];
}

const MAX_POINTS = 120;

const escapeHtml = (value) => {
	if (value === undefined || value === null) {
		return "";
	}
	return String(value)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#39;");
};

const downsample = (labels, seriesCollection) => {
	if (!labels.length || labels.length <= MAX_POINTS) {
		return {
			labels: labels.length ? labels : ["Aucune donnée"],
			series: seriesCollection.map((series) => (series.length ? series : [0])),
		};
	}

	const step = Math.ceil(labels.length / MAX_POINTS);
	const sampledLabels = [];
	const sampledSeries = seriesCollection.map(() => []);

	for (let index = 0; index < labels.length; index += step) {
		sampledLabels.push(labels[index]);
		seriesCollection.forEach((series, seriesIndex) => {
			sampledSeries[seriesIndex].push(series[index]);
		});
	}

	return { labels: sampledLabels, series: sampledSeries };
};

document.addEventListener("DOMContentLoaded", () => {
	const labels = dailyData.map((item) => item.date);
	const followersAdded = dailyData.map((item) => item.followers_added || 0);
	const followersRemoved = dailyData.map((item) => item.followers_removed || 0);
	const followersNet = dailyData.map((item) => item.followers_net || 0);
	const followingAdded = dailyData.map((item) => item.following_added || 0);
	const followingRemoved = dailyData.map((item) => item.following_removed || 0);
	const followingNet = dailyData.map((item) => item.following_net || 0);

	const { labels: reducedLabels, series } = downsample(labels, [
		followersAdded,
		followersRemoved,
		followersNet,
		followingAdded,
		followingRemoved,
		followingNet,
	]);

	const [followersAddedSeries, followersRemovedSeries, followersNetSeries, followingAddedSeries, followingRemovedSeries, followingNetSeries] = series;

	const buildChart = (canvasId, datasets) => {
		const canvas = document.getElementById(canvasId);
		if (!canvas) {
			return;
		}

		return new Chart(canvas, {
			type: "line",
			data: {
				labels: reducedLabels,
				datasets,
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				animation: false,
				transitions: {
					active: { animation: { duration: 0 } },
					resize: { animation: { duration: 0 } },
				},
				interaction: {
					mode: "nearest",
					axis: "x",
					intersect: false,
				},
				plugins: {
					legend: {
						labels: {
							usePointStyle: true,
						},
					},
					tooltip: {
						mode: "index",
						intersect: false,
					},
					decimation: {
						enabled: true,
						algorithm: "lttb",
						samples: MAX_POINTS,
					},
				},
				elements: {
					line: {
						tension: 0.35,
						borderWidth: 2,
					},
					point: {
						radius: 3,
						hoverRadius: 4,
					},
				},
				scales: {
					y: {
						beginAtZero: true,
						grid: {
							color: "rgba(148, 163, 184, 0.12)",
						},
						border: {
							color: "rgba(148, 163, 184, 0.2)",
						},
					},
					x: {
						grid: {
							display: false,
						},
						border: {
							color: "rgba(148, 163, 184, 0.2)",
						},
					},
				},
			},
		});
	};

	buildChart("followersChart", [
		{
			label: "Followers +",
			data: followersAddedSeries,
			borderColor: "#38bdf8",
			backgroundColor: "rgba(56, 189, 248, 0.15)",
			fill: false,
		},
		{
			label: "Followers -",
			data: followersRemovedSeries,
			borderColor: "#f87171",
			backgroundColor: "rgba(248, 113, 113, 0.15)",
			fill: false,
		},
		{
			label: "Net followers",
			data: followersNetSeries,
			borderColor: "#34d399",
			backgroundColor: "rgba(52, 211, 153, 0.2)",
			fill: false,
			borderDash: [6, 4],
		},
	]);

	buildChart("followingChart", [
		{
			label: "Following +",
			data: followingAddedSeries,
			borderColor: "#a855f7",
			backgroundColor: "rgba(168, 85, 247, 0.18)",
			fill: false,
		},
		{
			label: "Following -",
			data: followingRemovedSeries,
			borderColor: "#facc15",
			backgroundColor: "rgba(250, 204, 21, 0.15)",
			fill: false,
		},
		{
			label: "Net following",
			data: followingNetSeries,
			borderColor: "#6366f1",
			backgroundColor: "rgba(99, 102, 241, 0.2)",
			fill: false,
			borderDash: [6, 4],
		},
	]);

	const buildRelationshipChart = () => {
		const canvas = document.getElementById("relationshipChart");
		if (!canvas || typeof Chart === "undefined") {
			return;
		}
		const mutual = relationshipsData.mutual_total || 0;
		const onlyFollowers = relationshipsData.only_followers_total || 0;
		const onlyFollowing = relationshipsData.only_following_total || 0;
		return new Chart(canvas, {
			type: "doughnut",
			data: {
				labels: ["Mutuels", "Followers uniquement", "Following uniquement"],
				datasets: [
					{
						label: "Répartition",
						data: [mutual, onlyFollowers, onlyFollowing],
						backgroundColor: ["#34d399", "#38bdf8", "#fbbf24"],
						borderColor: "rgba(15, 23, 42, 0.9)",
						borderWidth: 2,
					},
				],
			},
			options: {
				plugins: {
					legend: {
						position: "bottom",
					},
				},
			},
		});
	};

	const buildTotalsChart = () => {
		const canvas = document.getElementById("totalsChart");
		if (!canvas || typeof Chart === "undefined") {
			return;
		}
		const followersTotal = relationshipsData.followers_total || 0;
		const followingTotal = relationshipsData.following_total || 0;
		return new Chart(canvas, {
			type: "bar",
			data: {
				labels: ["Followers", "Following"],
				datasets: [
					{
						label: "Comptes",
						data: [followersTotal, followingTotal],
						backgroundColor: ["rgba(56, 189, 248, 0.6)", "rgba(99, 102, 241, 0.6)"],
						borderRadius: 12,
					},
				],
			},
			options: {
				indexAxis: "y",
				plugins: {
					legend: { display: false },
				},
				scales: {
					x: {
						beginAtZero: true,
						grid: { color: "rgba(148, 163, 184, 0.15)" },
					},
					y: {
						grid: { display: false },
					},
				},
			},
		});
	};

	buildRelationshipChart();
	buildTotalsChart();

	const statusElement = document.getElementById("actionStatus");
	const filtersForm = document.querySelector(".filters");
	const accountSelect = document.getElementById("account");
	const daysSelect = document.getElementById("days");
	const startDateInput = document.getElementById("start");
	const endDateInput = document.getElementById("end");
	const chartsRow = document.querySelector(".panel-row");
	const toggleChartsBtn = document.getElementById("toggleChartsBtn");
	const runSnapshotBtn = document.getElementById("runSnapshotBtn");
	const viewReportBtn = document.getElementById("viewReportBtn");
	const startScheduleBtn = document.getElementById("startScheduleBtn");
	const reportModal = document.getElementById("reportModal");
	const reportModalBody = document.getElementById("reportModalBody");
	const aiForm = document.getElementById("aiChatForm");
	const aiQuestionInput = document.getElementById("aiQuestion");
	const aiTranscript = document.getElementById("aiTranscript");
	const aiStatus = document.getElementById("aiStatus");

	const showStatus = (message, variant = "info") => {
		if (!statusElement) {
			return;
		}
		statusElement.textContent = message;
		statusElement.classList.remove("action-status--success", "action-status--error", "action-status--info");
		statusElement.classList.add(`action-status--${variant}`);
		statusElement.hidden = false;
	};

	const clearStatus = () => {
		if (statusElement) {
			statusElement.textContent = "";
			statusElement.hidden = true;
		}
	};

	const toggleCharts = () => {
		const hidden = document.body.classList.toggle("charts-hidden");
		if (toggleChartsBtn) {
			toggleChartsBtn.textContent = hidden ? "Afficher les graphiques" : "Masquer les graphiques";
		}
		if (hidden) {
			showStatus("Graphiques masqués. Cliquez de nouveau pour les afficher.", "info");
		} else {
			clearStatus();
		}
	};

	const getSelectedAccount = () => accountSelect?.value || "";
	const getSelectedDays = () => {
		if (daysSelect && daysSelect.value) {
			return parseInt(daysSelect.value, 10);
		}
		return filtersForm?.dataset.defaultDays ? parseInt(filtersForm.dataset.defaultDays, 10) : 7;
	};
	const getSelectedStart = () => startDateInput?.value || "";
	const getSelectedEnd = () => endDateInput?.value || "";
	const getActiveAccount = () => getSelectedAccount() || defaultAccount || "";

	const handleSnapshot = async () => {
		showStatus("Capture en cours…", "info");
		try {
			const response = await fetch("/api/snapshot", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
			});
			const payload = await response.json();
			if (!response.ok) {
				throw new Error(payload.message || "Échec de la capture");
			}
			showStatus("Capture terminée. Rafraîchissez la page pour voir les nouvelles données.", "success");
		} catch (error) {
			showStatus(error.message || "Impossible de lancer la capture", "error");
		}
	};

	const setAiStatus = (message, variant = "info") => {
		if (!aiStatus) {
			return;
		}
		aiStatus.textContent = message;
		aiStatus.dataset.variant = variant;
		aiStatus.hidden = !message;
	};

	const appendBubble = (message, role) => {
		if (!aiTranscript) {
			return null;
		}
		const bubble = document.createElement("div");
		bubble.className = `ai-bubble ai-bubble--${role}`;
		bubble.textContent = message;
		aiTranscript.appendChild(bubble);
		aiTranscript.scrollTop = aiTranscript.scrollHeight;
		return bubble;
	};

	const handleAiSubmit = async (event) => {
		event.preventDefault();
		if (!aiEnabled) {
			return;
		}
		const question = aiQuestionInput?.value.trim();
		if (!question) {
			setAiStatus("Posez une question avant d'envoyer.", "error");
			return;
		}
		const account = getActiveAccount();
		if (!account) {
			setAiStatus("Sélectionnez un compte pour interroger l'IA.", "error");
			return;
		}
		setAiStatus("Analyse en cours…", "info");
		appendBubble(question, "user");
		const placeholder = appendBubble("✳️ L'assistant réfléchit…", "assistant");
		try {
			const response = await fetch("/api/ai/chat", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ account, question }),
			});
			const payload = await response.json();
			if (!response.ok) {
				throw new Error(payload.message || "Impossible d'obtenir une réponse.");
			}
			if (placeholder) {
				placeholder.textContent = payload.answer || "Réponse vide.";
			}
			setAiStatus("Réponse générée.", "success");
			if (aiQuestionInput) {
				aiQuestionInput.value = "";
			}
		} catch (error) {
			const message = error instanceof Error ? error.message : "Erreur IA inattendue.";
			if (placeholder) {
				placeholder.textContent = `❌ ${message}`;
			}
			setAiStatus(message, "error");
		}
	};

	if (aiForm && aiEnabled) {
		aiForm.addEventListener("submit", handleAiSubmit);
	}

	const renderReportModal = (payload) => {
		if (!reportModal || !reportModalBody) {
			return;
		}
		const { counts = {}, insights = {}, recent = [], totals = {}, gaps = {}, comparison = {}, history = {} } = payload;
		const countsList = Object.entries(counts)
			.map(([key, value]) => `<li><span>${escapeHtml(key)}</span><strong>${escapeHtml(value)}</strong></li>`)
			.join("");
		const insightsList = Object.entries(insights)
			.filter(([key]) => !["top_new_followers", "top_lost_followers", "latest_activity", "best_day", "worst_day"].includes(key))
			.map(([key, value]) => `<li><span>${escapeHtml(key)}</span><strong>${escapeHtml(value)}</strong></li>`)
			.join("");
		const latestActivity = insights.latest_activity
			? `<p class="modal__meta">Dernière activité: ${escapeHtml(insights.latest_activity.detected_at)}</p>`
			: "";
		const bestDay = insights.best_day
			? `<p class="modal__meta">Jour record: ${escapeHtml(insights.best_day.date)} (+${escapeHtml(insights.best_day.followers_net)} followers)</p>`
			: "";
		const worstDay = insights.worst_day
			? `<p class="modal__meta">Jour calme: ${escapeHtml(insights.worst_day.date)} (${escapeHtml(insights.worst_day.followers_net)} followers)</p>`
			: "";
		const renderChanges = (changes) =>
			changes
				.map(
					(change) => `
						<li>
							<span>${escapeHtml(change.detected_at)} · ${escapeHtml(change.list_type)} ${escapeHtml(change.change_type)}</span>
							<strong>${escapeHtml(change.username || change.full_name || "—")}</strong>
						</li>
					`
				)
				.join("");
		const topNew = renderChanges(insights.top_new_followers || []);
		const topLost = renderChanges(insights.top_lost_followers || []);
		const recentItems = renderChanges(recent);
		const totalsList = Object.entries(totals)
			.map(([key, value]) => `<li><span>${escapeHtml(key)}</span><strong>${escapeHtml(value)}</strong></li>`)
			.join("");
		const notBack = Array.isArray(gaps.not_following_you_back?.users) ? gaps.not_following_you_back.users : [];
		const notBackCount = gaps.not_following_you_back?.count ?? notBack.length;
		const youDontBack = Array.isArray(gaps.you_dont_follow_back?.users) ? gaps.you_dont_follow_back.users : [];
		const youDontBackCount = gaps.you_dont_follow_back?.count ?? youDontBack.length;
		const renderGapUsers = (users) =>
			users
				.map((user) => {
					const primary = user?.username || user?.full_name || "—";
					const secondary = user?.full_name && user?.username && user.full_name !== user.username ? user.full_name : "";
					return `
						<li>
							<span>${escapeHtml(primary)}</span>
							${secondary ? `<strong>${escapeHtml(secondary)}</strong>` : ""}
						</li>
					`;
				})
				.join("");
		const formatDateTime = (value) => (value ? escapeHtml(String(value).replace("T", " ")) : "—");
		const gapsSection = `
			<section>
				<h4>Who Doesn’t Follow Back</h4>
				<div class="modal-grid">
					<div>
						<h5>Not Following You Back (${escapeHtml(notBackCount)})</h5>
						<ul class="modal-list">${renderGapUsers(notBack) || "<li>Aucun écart</li>"}</ul>
					</div>
					<div>
						<h5>You Don’t Follow Back (${escapeHtml(youDontBackCount)})</h5>
						<ul class="modal-list">${renderGapUsers(youDontBack) || "<li>Aucun écart</li>"}</ul>
					</div>
				</div>
			</section>
		`;
		const renderComparisonUsers = (users) =>
			users
				.map(
					(user) => `
						<li>
							<span>${escapeHtml(user.username || user.full_name || "—")}</span>
							${user.full_name && user.username && user.full_name !== user.username ? `<strong>${escapeHtml(user.full_name)}</strong>` : ""}
						</li>
					`
				)
				.join("");
		const renderComparisonSection = () => {
			if (!comparison || !comparison.available) {
				return "";
			}
			const listTypes = [
				["followers", "Followers"],
				["following", "Following"],
			];
			const columns = listTypes
				.map(([key, label]) => {
					const section = comparison[key] || {};
					const baseline = section.baseline || {};
					const current = section.current || {};
					return `
						<div>
							<h5>${escapeHtml(label)}</h5>
							<ul class="modal-list">
								<li><span>Snapshot initial</span><strong>${formatDateTime(baseline.collected_at)}</strong></li>
								<li><span>Compte initial</span><strong>${escapeHtml(baseline.count ?? 0)}</strong></li>
								<li><span>Snapshot final</span><strong>${formatDateTime(current.collected_at)}</strong></li>
								<li><span>Compte final</span><strong>${escapeHtml(current.count ?? 0)}</strong></li>
							</ul>
							<div class="modal-grid">
								<div>
									<h6>Ajouts (${escapeHtml(section.added_total ?? 0)})</h6>
									<ul class="modal-list">${renderComparisonUsers(section.added || []) || "<li>Aucun ajout.</li>"}</ul>
								</div>
								<div>
									<h6>Suppressions (${escapeHtml(section.removed_total ?? 0)})</h6>
									<ul class="modal-list">${renderComparisonUsers(section.removed || []) || "<li>Aucune suppression.</li>"}</ul>
								</div>
							</div>
						</div>
					`;
				})
				.join("");
			return `
				<section>
					<h4>Comparaison des snapshots</h4>
					<div class="modal-grid">${columns}</div>
				</section>
			`;
		};
		const renderHistorySection = () => {
			const followersHistory = Array.isArray(history.followers) ? history.followers : [];
			const followingHistory = Array.isArray(history.following) ? history.following : [];
			if (!followersHistory.length && !followingHistory.length) {
				return "";
			}
			const buildList = (entries) =>
				entries
					.map(
						(entry) => `
							<li>
								<span>${formatDateTime(entry.collected_at)}</span>
								<strong>${escapeHtml(entry.count ?? 0)} comptes</strong>
							</li>
						`
					)
					.join("");
			return `
				<section>
					<h4>Archives des snapshots</h4>
					<div class="modal-grid">
						<div>
							<h5>Followers</h5>
							<ul class="modal-list">${buildList(followersHistory) || "<li>Aucune archive.</li>"}</ul>
						</div>
						<div>
							<h5>Following</h5>
							<ul class="modal-list">${buildList(followingHistory) || "<li>Aucune archive.</li>"}</ul>
						</div>
					</div>
				</section>
			`;
		};
		const comparisonSection = renderComparisonSection();
		const historySection = renderHistorySection();

		reportModalBody.innerHTML = `
			<section>
				<h4>Totaux</h4>
				<ul class="modal-list">${totalsList}</ul>
			</section>
			<section>
				<h4>Compteurs période</h4>
				<ul class="modal-list">${countsList}</ul>
			</section>
			<section>
				<h4>Insights</h4>
				${latestActivity}${bestDay}${worstDay}
				<ul class="modal-list">${insightsList}</ul>
				<div class="modal-grid">
					<div>
						<h5>Top entrées</h5>
						<ul class="modal-list">${topNew || "<li>Aucune entrée récente.</li>"}</ul>
					</div>
					<div>
						<h5>Top sorties</h5>
						<ul class="modal-list">${topLost || "<li>Aucune sortie récente.</li>"}</ul>
					</div>
				</div>
			</section>
			${gapsSection}
			${comparisonSection}
			${historySection}
			<section>
				<h4>Derniers événements (${recent.length})</h4>
				<ul class="modal-list modal-list--scroll">${recentItems || "<li>Aucun événement.</li>"}</ul>
			</section>
		`;
		reportModal.hidden = false;
		reportModal.classList.add("modal--open");
		reportModal.focus?.();
	};

	const closeModal = () => {
		if (reportModal) {
			reportModal.classList.remove("modal--open");
			reportModal.hidden = true;
		}
	};

	const handleReport = async () => {
		showStatus("Récupération du rapport…", "info");
		try {
			const params = new URLSearchParams();
			const account = getSelectedAccount();
			const days = getSelectedDays();
			const start = getSelectedStart();
			const end = getSelectedEnd();
			if (account) {
				params.set("account", account);
			}
			params.set("days", String(days));
			params.set("preview_limit", "50");
			if (start) {
				params.set("start", start);
			}
			if (end) {
				params.set("end", end);
			}
			const response = await fetch(`/api/report?${params.toString()}`);
			const payload = await response.json();
			if (!response.ok || payload.status !== "ok") {
				throw new Error(payload.message || "Échec du chargement du rapport");
			}
			renderReportModal(payload);
			clearStatus();
		} catch (error) {
			showStatus(error.message || "Impossible de charger le rapport", "error");
		}
	};

	const handleSchedule = async () => {
		showStatus("Activation de la planification…", "info");
		try {
			const response = await fetch("/api/schedule", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
			});
			const payload = await response.json();
			if (!response.ok || payload.status !== "ok") {
				throw new Error(payload.message || "Impossible d'activer la planification");
			}
			showStatus(payload.message || "Planification activée", "success");
		} catch (error) {
			showStatus(error.message || "Impossible d'activer la planification", "error");
		}
	};

	if (toggleChartsBtn && chartsRow) {
		toggleChartsBtn.addEventListener("click", toggleCharts);
	}

	if (runSnapshotBtn) {
		runSnapshotBtn.addEventListener("click", handleSnapshot);
	}

	if (viewReportBtn) {
		viewReportBtn.addEventListener("click", handleReport);
	}

	if (startScheduleBtn) {
		startScheduleBtn.addEventListener("click", handleSchedule);
	}

	if (reportModal) {
		reportModal.addEventListener("click", (event) => {
			const target = event.target;
			if (target instanceof HTMLElement && target.dataset.close === "modal") {
				closeModal();
			}
		});
		document.addEventListener("keydown", (event) => {
			if (event.key === "Escape" && !reportModal.hidden) {
				closeModal();
			}
		});
	}

	const scheduleAutoRefresh = () => {
		if (!autoRefreshSeconds || autoRefreshSeconds < 30) {
			return;
		}
		const formatDelay = () => {
			if (autoRefreshSeconds < 60) {
				return `${autoRefreshSeconds} s`;
			}
			const minutes = autoRefreshSeconds / 60;
			if (minutes >= 120) {
				const hours = minutes / 60;
				return `${hours.toFixed(hours % 1 === 0 ? 0 : 1)} h`;
			}
			return `${minutes.toFixed(minutes % 1 === 0 ? 0 : 1)} min`;
		};
		if (statusElement && statusElement.hidden) {
			showStatus(`Rafraîchissement automatique dans ${formatDelay()}.`, "info");
			statusElement.dataset.autorefresh = "true";
		}
		setTimeout(() => {
			window.location.reload();
		}, autoRefreshSeconds * 1000);
	};

	scheduleAutoRefresh();
});
