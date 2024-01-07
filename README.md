# liaozhiming.github.io

#### nginx部署需注意
```js
# vue redirect
    location / {
      try_files $uri $uri/ /index.html;
    }
```

#### Github Page部署需注意
Github pages 里不能这样做，只能借助 404.html ，当 Github pages 找不到页面时会自动寻找根目录下的 404.html 文件，那我们多拷贝一份与 index.html 相同的文件命名为 404.html 即可解决这个问题。
```yaml
- name: Build
  run: |
    npm run build
    cp dist/index.html dist/404.html
```