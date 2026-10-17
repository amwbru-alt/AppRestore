'use strict';
if (document.body.dataset.refresh) {
  window.setTimeout(() => { if (!document.hidden) window.location.reload(); }, 7000);
}
for (const form of document.querySelectorAll('[data-image-form]')) {
  const fileInput = form.querySelector('[data-image-file]');
  let loading = false;
  fileInput.addEventListener('change', async () => {
    const field = form.querySelector('[name=image_data]');
    const error = form.querySelector('[data-upload-error]');
    const file = fileInput.files[0];
    field.value = ''; error.textContent = ''; loading = false;
    if (!file) return;
    if (file.size > 2000000 || !['image/png', 'image/jpeg'].includes(file.type)) {
      error.textContent = 'Выберите PNG или JPEG размером до 2 МБ.';
      fileInput.value = ''; return;
    }
    loading = true;
    try {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject; reader.readAsDataURL(file);
      });
      field.value = data;
    } catch { error.textContent = 'Не удалось прочитать фото. Выберите файл заново.'; }
    finally { loading = false; }
  });
  form.addEventListener('submit', event => {
    if (loading) { event.preventDefault(); form.querySelector('[data-upload-error]').textContent = 'Подождите, фото ещё загружается.'; }
  });
}
