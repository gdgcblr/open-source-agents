// A browser refresh starts a fresh conversation through the CSRF-protected reset.
const navigation = performance.getEntriesByType('navigation')[0];
const newChat = document.getElementById('new-chat');
if (navigation?.type === 'reload' && newChat) {
  document.body.hidden = true;
  newChat.requestSubmit();
} else {
// Keep status text local; never log form values or provider responses.
const conversation = document.querySelector('.chat-history');
if (conversation) conversation.scrollTop = conversation.scrollHeight;
document.querySelectorAll('form[data-progress]').forEach(form => {
  form.addEventListener('submit', () => {
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    button.textContent = form.dataset.progress;
    button.setAttribute('aria-live', 'polite');
  });
});
window.addEventListener('pageshow', event => {
  if (event.persisted) window.location.reload();
});

}
