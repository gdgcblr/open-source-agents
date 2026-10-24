const questionInput = document.getElementById('questionInput');
const askButton = document.getElementById('askButton');
const clearButton = document.getElementById('clearButton');
const responseBox = document.getElementById('responseBox');
const loadingBadge = document.getElementById('loadingBadge');
const chips = document.querySelectorAll('.chip');

function setResponse(message, isError = false) {
  responseBox.classList.remove('empty', 'error');
  if (isError) responseBox.classList.add('error');
  responseBox.textContent = message;
}

function setLoading(isLoading) {
  loadingBadge.classList.toggle('hidden', !isLoading);
  askButton.disabled = isLoading;
  askButton.style.opacity = isLoading ? '0.7' : '1';
}

async function askAssistant() {
  const question = questionInput.value.trim();

  if (!question) {
    setResponse('Please enter a question first.', true);
    questionInput.focus();
    return;
  }

  setLoading(true);
  setResponse('Thinking...');

  try {
    console.log('Sending question to /ask:', question);
    const response = await fetch('/ask', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ question })
    });

    const data = await response.json();
    console.log('API response status:', response.status, data);

    if (!response.ok) {
      throw new Error(data.error || 'Something went wrong.');
    }

    const rawAnswer = data.answer;
    const answer = Array.isArray(rawAnswer)
      ? rawAnswer.map(item => item.text || '').join('\n\n')
      : typeof rawAnswer === 'object'
        ? JSON.stringify(rawAnswer)
        : rawAnswer || 'No answer returned.';

    setResponse(answer);
  } catch (error) {
    console.error('Fetch error:', error);
    setResponse(error.message || 'Failed to get a response.', true);
  } finally {
    setLoading(false);
  }
}

askButton.addEventListener('click', askAssistant);
clearButton.addEventListener('click', () => {
  questionInput.value = '';
  setResponse('Your answer will appear here.');
  responseBox.classList.add('empty');
  questionInput.focus();
});

chips.forEach((chip) => {
  chip.addEventListener('click', () => {
    questionInput.value = chip.textContent.trim();
    questionInput.focus();
  });
});

questionInput.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    askAssistant();
  }
});
