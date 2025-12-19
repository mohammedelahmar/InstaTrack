const script = document.currentScript;
let initialSettings = {};

if (script && script.dataset.settings) {
	try {
		initialSettings = JSON.parse(script.dataset.settings);
	} catch (error) {
		console.error("Impossible de parser les paramètres initiaux", error);
	}
}

const state = {
	targetAccounts: Array.isArray(initialSettings.target_accounts) ? [...initialSettings.target_accounts] : [],
	autoRefreshSeconds: Number(initialSettings.auto_refresh_seconds || 0),
	pendingProfile: null,
};

const elements = {
	status: document.getElementById("settingsStatus"),
	accountForm: document.getElementById("accountForm"),
	accountInput: document.getElementById("accountInput"),
	accountResult: document.getElementById("accountResult"),
	accountResultTitle: document.getElementById("accountResultTitle"),
	accountResultDescription: document.getElementById("accountResultDescription"),
	accountResultActions: document.getElementById("accountResultActions"),
	inlineSessionForm: document.getElementById("inlineSessionForm"),
	inlineSessionInput: document.getElementById("inlineSessionInput"),
	inlineSessionPersist: document.getElementById("inlineSessionPersist"),
	inlineSessionCancel: document.getElementById("inlineSessionCancel"),
	accountsList: document.getElementById("accountsList"),
	sessionMask: document.getElementById("sessionMask"),
	sessionForm: document.getElementById("sessionForm"),
	sessionInput: document.getElementById("sessionInput"),
	sessionPersist: document.getElementById("sessionPersist"),
	sessionClear: document.getElementById("sessionClear"),
	autoRefreshForm: document.getElementById("autoRefreshForm"),
	autoRefreshInput: document.getElementById("autoRefreshMinutes"),
	autoRefreshLabel: document.getElementById("autoRefreshLabel"),
};

elements.inlineSessionPersist.checked = false;

const formatAutoRefresh = (seconds) => {
	if (!seconds) {
		return "Désactivé";
	}
	if (seconds < 60) {
		return `${seconds} s`;
	}
	const minutes = seconds / 60;
	if (minutes >= 120) {
		const hours = minutes / 60;
		return `${hours.toFixed(hours % 1 === 0 ? 0 : 1)} h`;
	}
	return `${minutes.toFixed(minutes % 1 === 0 ? 0 : 1)} min`;
};

const updateAutoRefreshUI = () => {
	elements.autoRefreshLabel.textContent = formatAutoRefresh(state.autoRefreshSeconds);
	const minutesValue = state.autoRefreshSeconds ? state.autoRefreshSeconds / 60 : 0;
	elements.autoRefreshInput.value = minutesValue && !Number.isNaN(minutesValue) ? minutesValue : 0;
};

const showStatus = (message, variant = "info") => {
	if (!elements.status) {
		return;
	}
	elements.status.textContent = message;
	elements.status.classList.remove("action-status--info", "action-status--success", "action-status--error");
	elements.status.classList.add(`action-status--${variant}`);
	elements.status.hidden = false;
};

const clearStatus = () => {
	if (!elements.status) {
		return;
	}
	elements.status.textContent = "";
	elements.status.hidden = true;
};

const requestJson = async (url, options = {}) => {
	const response = await fetch(url, {
		...options,
		headers: {
			"Content-Type": "application/json",
			...(options.headers || {}),
		},
	});

	let payload = {};
	try {
		payload = await response.json();
	} catch (error) {
		// ignore parse errors
	}

	if (!response.ok || payload.status === "error") {
		const errorMessage = payload.message || "Erreur inattendue";
		throw new Error(errorMessage);
	}

	return payload;
};

const renderAccounts = () => {
	elements.accountsList.innerHTML = "";
	if (!state.targetAccounts.length) {
		const empty = document.createElement("li");
		empty.className = "settings-chip settings-chip--empty";
		empty.textContent = "Aucun compte suivi pour le moment.";
		elements.accountsList.append(empty);
		return;
	}

	state.targetAccounts.forEach((account) => {
		const item = document.createElement("li");
		item.className = "settings-chip";

		const label = document.createElement("span");
		label.textContent = `@${account}`;

		const removeButton = document.createElement("button");
		removeButton.type = "button";
		removeButton.className = "chip-remove";
		removeButton.dataset.username = account;
		removeButton.textContent = "Retirer";

		item.append(label, removeButton);
		elements.accountsList.append(item);
	});
};

const resetAccountResult = () => {
	elements.accountResult.hidden = true;
	elements.accountResultTitle.textContent = "";
	elements.accountResultDescription.textContent = "";
	elements.accountResultActions.innerHTML = "";
	elements.inlineSessionForm.hidden = true;
	elements.inlineSessionInput.value = "";
	state.pendingProfile = null;
};

const handleAddAccount = async (username) => {
	const payload = await requestJson("/api/settings/accounts", {
		method: "POST",
		body: JSON.stringify({ username }),
	});
	if (Array.isArray(payload.accounts)) {
		state.targetAccounts = payload.accounts;
		renderAccounts();
	}
	showStatus(`Le compte @${username} a été ajouté.`, "success");
	resetAccountResult();
	return payload.accounts;
};

function renderAccountResult(profile) {
	if (!profile) {
		resetAccountResult();
		return;
	}
	elements.accountResult.hidden = false;
	const username = profile.username || elements.accountInput.value.trim();
	elements.accountResultTitle.textContent = profile.is_private
		? `@${username} est privé`
		: `@${username} est public`;

	const fullName = profile.full_name ? ` (${profile.full_name})` : "";
	if (profile.is_private) {
		elements.accountResultDescription.textContent = `Le compte${fullName} est privé. Choisissez une option pour accéder aux données.`;
		const followButton = document.createElement("button");
		followButton.type = "button";
		followButton.className = "btn btn--primary";
		followButton.textContent = "Envoyer une demande de suivi";
		followButton.addEventListener("click", async () => {
			try {
				showStatus("Envoi de la demande de suivi…", "info");
				const payload = await requestJson("/api/settings/follow-request", {
					method: "POST",
					body: JSON.stringify({ username, add_to_targets: true }),
				});
				if (Array.isArray(payload.accounts)) {
					state.targetAccounts = payload.accounts;
					renderAccounts();
				}
				const friendship = payload.result && payload.result.friendship_status;
				if (friendship && friendship.following) {
					showStatus(`Le compte @${username} est désormais suivi.`, "success");
				} else if (friendship && friendship.outgoing_request) {
					showStatus("Demande envoyée. Attendez l'acceptation pour collecter les données.", "info");
				} else {
					showStatus("Demande envoyée. Vérifiez Instagram pour confirmer.", "info");
				}
				resetAccountResult();
			} catch (error) {
				showStatus(error.message, "error");
			}
		});

		const sessionButton = document.createElement("button");
		sessionButton.type = "button";
		sessionButton.className = "btn btn--ghost";
		sessionButton.textContent = "Utiliser un session ID temporaire";
		sessionButton.addEventListener("click", () => {
			elements.inlineSessionForm.hidden = false;
			elements.inlineSessionInput.focus();
		});

		elements.accountResultActions.innerHTML = "";
		elements.accountResultActions.append(followButton, sessionButton);
	} else {
		elements.accountResultDescription.textContent = `Le compte${fullName} est public. Vous pouvez l'ajouter directement.`;
		const addButton = document.createElement("button");
		addButton.type = "button";
		addButton.className = "btn btn--primary";
		addButton.textContent = "Ajouter ce compte";
		addButton.addEventListener("click", () => {
			handleAddAccount(username).catch((error) => showStatus(error.message, "error"));
		});
		elements.accountResultActions.innerHTML = "";
		elements.accountResultActions.append(addButton);
		elements.inlineSessionForm.hidden = true;
	}
}

const handleCheckAccount = async (event) => {
	event.preventDefault();
	const username = elements.accountInput.value.trim();
	if (!username) {
		showStatus("Veuillez saisir un nom d'utilisateur.", "error");
		return;
	}
	clearStatus();
	showStatus("Vérification du compte en cours…", "info");
	try {
		const payload = await requestJson("/api/settings/account-check", {
			method: "POST",
			body: JSON.stringify({ username }),
		});
		state.pendingProfile = payload;
		renderAccountResult(payload);
		showStatus("Analyse terminée.", "success");
	} catch (error) {
		showStatus(error.message, "error");
		resetAccountResult();
	}
};

elements.accountForm.addEventListener("submit", handleCheckAccount);

elements.accountsList.addEventListener("click", async (event) => {
	const target = event.target;
	if (!(target instanceof HTMLElement)) {
		return;
	}
	if (target.matches(".chip-remove")) {
		const username = target.dataset.username;
		if (!username) {
			return;
		}
		try {
			const payload = await requestJson(`/api/settings/accounts/${encodeURIComponent(username)}`, {
				method: "DELETE",
			});
			if (Array.isArray(payload.accounts)) {
				state.targetAccounts = payload.accounts;
				renderAccounts();
			}
			showStatus(`Le compte @${username} a été retiré.`, "success");
		} catch (error) {
			showStatus(error.message, "error");
		}
	}
});

const handleInlineSessionSubmit = async (event) => {
	event.preventDefault();
	if (!state.pendingProfile) {
		showStatus("Veuillez analyser un compte privé avant de renseigner un session ID.", "error");
		return;
	}
	const username = state.pendingProfile.username || elements.accountInput.value.trim();
	const sessionId = elements.inlineSessionInput.value.trim();
	const persist = elements.inlineSessionPersist.checked;
	if (!sessionId) {
		showStatus("Le session ID est requis pour cette option.", "error");
		return;
	}
	try {
		showStatus("Mise à jour du session ID…", "info");
		const sessionPayload = await requestJson("/api/settings/session", {
			method: "POST",
			body: JSON.stringify({ session_id: sessionId, persist }),
		});
		elements.sessionMask.textContent = sessionPayload.session_mask || "••••";
		await handleAddAccount(username);
		showStatus(
			persist
				? "Session enregistrée et compte ajouté. Pensez à rétablir le cookie après usage."
				: "Session temporaire enregistrée. Lancez rapidement une capture pour éviter l'expiration.",
			"info",
		);
	} catch (error) {
		showStatus(error.message, "error");
	} finally {
		elements.inlineSessionForm.hidden = true;
		elements.inlineSessionInput.value = "";
	}
};

elements.inlineSessionForm.addEventListener("submit", handleInlineSessionSubmit);

elements.inlineSessionCancel.addEventListener("click", () => {
	elements.inlineSessionForm.hidden = true;
	elements.inlineSessionInput.value = "";
});

const handleSessionFormSubmit = async (event) => {
	event.preventDefault();
	const sessionId = elements.sessionInput.value.trim();
	const persist = elements.sessionPersist.checked;
	try {
		showStatus("Enregistrement du session ID…", "info");
		const payload = await requestJson("/api/settings/session", {
			method: "POST",
			body: JSON.stringify({ session_id: sessionId, persist }),
		});
		elements.sessionMask.textContent = payload.session_mask || "—";
		showStatus("Session mise à jour.", "success");
		elements.sessionInput.value = "";
	} catch (error) {
		showStatus(error.message, "error");
	}
};

elements.sessionForm.addEventListener("submit", handleSessionFormSubmit);

elements.sessionClear.addEventListener("click", async () => {
	try {
		showStatus("Suppression du session ID…", "info");
		await requestJson("/api/settings/session", {
			method: "POST",
			body: JSON.stringify({ session_id: null, persist: false }),
		});
		elements.sessionMask.textContent = "—";
		showStatus("Session supprimée.", "success");
	} catch (error) {
		showStatus(error.message, "error");
	}
});

const handleAutoRefreshSubmit = async (event) => {
	event.preventDefault();
	const rawValue = elements.autoRefreshInput.value;
	const minutes = parseFloat(rawValue);
	if (Number.isNaN(minutes) || minutes < 0) {
		showStatus("Valeur invalide pour l'intervalle.", "error");
		return;
	}
	const seconds = Math.round(minutes * 60);
	try {
		showStatus("Mise à jour de l'intervalle…", "info");
		const payload = await requestJson("/api/settings/auto-refresh", {
			method: "POST",
			body: JSON.stringify({ seconds }),
		});
		state.autoRefreshSeconds = payload.seconds || 0;
		updateAutoRefreshUI();
		showStatus("Intervalle enregistré.", "success");
	} catch (error) {
		showStatus(error.message, "error");
	}
};

elements.autoRefreshForm.addEventListener("submit", handleAutoRefreshSubmit);

renderAccounts();
updateAutoRefreshUI();
resetAccountResult();
clearStatus();
