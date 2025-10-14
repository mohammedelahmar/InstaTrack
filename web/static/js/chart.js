const scriptElement = document.currentScript;
let dailyData = [];

if (scriptElement) {
	const dataAttribute = scriptElement.dataset.daily;
	if (dataAttribute) {
		try {
			dailyData = JSON.parse(dataAttribute);
		} catch (error) {
			console.error("Unable to parse daily data", error);
		}
	}
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

	const statusElement = document.getElementById("actionStatus");
	const filtersForm = document.querySelector(".filters");
	const accountSelect = document.getElementById("account");
	const daysSelect = document.getElementById("days");
	const chartsRow = document.querySelector(".panel-row");
	const toggleChartsBtn = document.getElementById("toggleChartsBtn");
	const runSnapshotBtn = document.getElementById("runSnapshotBtn");
	const viewReportBtn = document.getElementById("viewReportBtn");
	const startScheduleBtn = document.getElementById("startScheduleBtn");
	const reportModal = document.getElementById("reportModal");
	const reportModalBody = document.getElementById("reportModalBody");

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

	const renderReportModal = (payload) => {
		if (!reportModal || !reportModalBody) {
			return;
		}
		const { counts = {}, insights = {}, recent = [], totals = {}, gaps = {} } = payload;
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
			if (account) {
				params.set("account", account);
			}
			params.set("days", String(days));
			params.set("preview_limit", "50");
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
});
