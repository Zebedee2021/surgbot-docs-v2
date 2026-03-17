// 自动标记页面最后更新时间
document.addEventListener('DOMContentLoaded', function () {
  const footer = document.querySelector('.doc-footer');
  if (footer) {
    const spans = footer.querySelectorAll('span');
    spans.forEach(span => {
      if (span.textContent.includes('最近更新')) {
        span.style.color = 'var(--md-default-fg-color--light)';
      }
    });
  }
});
