const webpack = require('webpack')
const {defineConfig} = require('@vue/cli-service')

const {GitRevisionPlugin} = require('git-revision-webpack-plugin');
const gitRevisionPlugin = new GitRevisionPlugin();

// 格式化构建时间为 YYYY-MM-DD HH:mm:ss
function formatBuildTime(date) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
        + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

// git 信息获取容错: 当 git 不可用或命令执行失败时,降级为默认值,避免构建中断
function safeGit(fn, fallback) {
    try {
        return fn();
    } catch (e) {
        console.warn('[vue.config] 获取 git 信息失败,使用降级值:', e.message);
        return fallback;
    }
}

module.exports = defineConfig({
    transpileDependencies: true,
    // 打包不生成map文件
    productionSourceMap: false,
    configureWebpack: {
        plugins: [
            new webpack.DefinePlugin({
                'process.env.COMMIT_VERSION': JSON.stringify(safeGit(() => gitRevisionPlugin.version(), 'unknown')),
                'process.env.COMMIT_HASH': JSON.stringify(safeGit(() => gitRevisionPlugin.commithash(), 'unknown')),
                'process.env.BRANCH': JSON.stringify(safeGit(() => gitRevisionPlugin.branch(), 'unknown')),
                'process.env.BUILD_TIME': JSON.stringify(formatBuildTime(new Date()))
            }),
        ]
    }
})
