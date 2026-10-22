'use strict';
const form = document.getElementById('analyze-form');
if (form) form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  const output = document.getElementById('analysis-result');
  button.disabled = true;
  output.replaceChildren();
  output.textContent = 'Reading your review…';
  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'X-CSRFToken':document.querySelector('meta[name="csrf-token"]').content},
      body: JSON.stringify({text:document.getElementById('review-input').value, save:document.getElementById('save-analysis')?.checked || false})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Analysis could not be completed.');
    output.replaceChildren();
    const label = document.createElement('strong');
    label.className = `result-label ${data.label.toLowerCase()}`;
    label.textContent = data.label;
    const description = document.createElement('p');
    description.textContent = `Positive estimate: ${(data.positive_probability*100).toFixed(1)}% · Negative: ${(data.negative_probability*100).toFixed(1)}%`;
    const note = document.createElement('p');
    note.className = 'fineprint';
    note.textContent = `Uncalibrated binary model estimates.${data.saved ? ' Saved to your private history.' : ' This analysis was not saved.'}`;
    output.append(label, description, note);
  } catch (error) {
    output.textContent = error.message || 'Connection failed. Please try again.';
  } finally {
    button.disabled = false;
  }
});
