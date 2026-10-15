/** @type {import('tailwindcss').Config} */
module.exports = {
    // 扫描模板文件,按需生成工具类
    content: [
        "./public/index.html",
        "./src/**/*.{vue,js}",
    ],
    theme: {
        extend: {
            colors: {
                // 站点主色,与 TDesign 主色保持一致
                brand: {
                    DEFAULT: '#0052d9',
                    light: '#4086ff',
                    dark: '#003cab',
                },
            },
        },
    },
    plugins: [],
    // TDesign 自带样式基线,关闭 Tailwind preflight 避免互相覆盖
    corePlugins: {
        preflight: false,
    },
}
