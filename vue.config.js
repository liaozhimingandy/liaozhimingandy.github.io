const webpack = require('webpack')
const {defineConfig} = require('@vue/cli-service')

const {GitRevisionPlugin} = require('git-revision-webpack-plugin');
const gitRevisionPlugin = new GitRevisionPlugin();
const moment = require("moment");

module.exports = defineConfig({
    transpileDependencies: true,
    // 打包不生成map文件
    productionSourceMap: false,
    configureWebpack: {
        plugins: [
            new webpack.DefinePlugin({
                'process.env.COMMIT_VERSION': JSON.stringify(gitRevisionPlugin.version()),
                'process.env.COMMIT_HASH': JSON.stringify(gitRevisionPlugin.commithash()),
                'process.env.BRANCH': JSON.stringify(gitRevisionPlugin.branch()),
                'process.env.BUILD_TIME': JSON.stringify(moment().format('YYYY-MM-DD hh:mm:ss'))

                ,
            }),
        ]
    }
})
