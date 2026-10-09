/**
 * 把 Blob 存成文件 —— **DOM 适配器**，跟 `utils/storage.js` 是同一类东西。
 *
 * ⚠️ 这是 `api/` 和 `stores/` 之外**唯一允许出现 `document`** 的地方。
 *    规矩的本意是「网络层和状态层必须可移植，平台差异锁进 `utils/` 的适配器」，
 *    而「下载」在 web 和 uniapp 上本来就是两套 API：这边是 `<a download>`，
 *    那边是 `uni.downloadFile` + `uni.saveFile`，`<a>` 根本不存在。
 *
 * 所以移植 uniapp 时要动的就这两个文件：`storage.js`（存储）+ `download.js`（下载）。
 */

/**
 * @param {Blob} blob
 * @param {string} filename 完整文件名（含 .xlsx）。空的话给个能看出来源的默认值
 */
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename || 'download.xlsx'

  // 有些浏览器要求链接在文档里才认 click()，加上再拿掉，代价是一次同步重排
  document.body.appendChild(link)
  link.click()
  link.remove()

  // ⚠️ 不能立刻 revoke：Safari 要等下载真的开始读取那个 URL 才认。
  //    但也不能不 revoke —— objectURL 会把整份文件钉在内存里，
  //    导十几个老师的表就是十几份 xlsx 一直不放。
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
