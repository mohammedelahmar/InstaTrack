document.addEventListener("DOMContentLoaded", () => {
	const canvas = document.getElementById("dailyChart");
	if (!canvas) {
		return;
	}

	const dataAttribute = document.currentScript?.dataset.daily;
	let dailyData = [];
	if (dataAttribute) {
		try {
			dailyData = JSON.parse(dataAttribute);
		} catch (error) {
			console.error("Unable to parse daily data", error);
		}
	}

	const labels = dailyData.map((item) => item.date);
	const followersAdded = dailyData.map((item) => item.followers_added || 0);
	const followersRemoved = dailyData.map((item) => item.followers_removed || 0);
	const followingAdded = dailyData.map((item) => item.following_added || 0);
	const followingRemoved = dailyData.map((item) => item.following_removed || 0);

	new Chart(canvas, {
		type: "line",
		data: {
			labels,
			datasets: [
				{
					label: "Followers +",
					data: followersAdded,
					borderColor: "#2ecc71",
					tension: 0.3,
				},
				{
					label: "Followers -",
					data: followersRemoved,
					borderColor: "#e74c3c",
					tension: 0.3,
				},
				{
					label: "Following +",
					data: followingAdded,
					borderColor: "#3498db",
					tension: 0.3,
				},
				{
					label: "Following -",
					data: followingRemoved,
					borderColor: "#f1c40f",
					tension: 0.3,
				},
			],
		},
		options: {
			responsive: true,
			maintainAspectRatio: false,
			scales: {
				y: {
					beginAtZero: true,
					precision: 0,
				},
			},
		},
	});
});
