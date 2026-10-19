(() => {
  const input = document.getElementById('id_uploads');
  const inventory = document.getElementById('research-file-inventory');
  const feedback = document.getElementById('upload-conflicts');
  const choice = document.getElementById('id_duplicate_action');
  const target = document.getElementById('id_logical_file');
  if (!input || !inventory || !feedback || !choice) return;
  const names = new Set(JSON.parse(inventory.textContent).map(file => file.name));
  const check = () => {
    const conflicts = Array.from(input.files).filter(file => names.has(file.name)).map(file => file.name);
    feedback.hidden = !conflicts.length;
    feedback.textContent = '检测到项目中已存在：' + conflicts.join('、') + '。请在「遇到同名文件时」选择上传为新版本或作为新的独立文件；取消可清除选择或离开页面。';
    choice.required = conflicts.length > 0 && !(target && target.value);
  };
  input.addEventListener('change', check);
  if (target) target.addEventListener('change', check);
})();
