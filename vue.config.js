const webpack = require('webpack')
const {defineConfig} = require('@vue/cli-service')
const { GitRevisionPlugin } = require('git-revision-webpack-plugin');
const gitRevisionPlugin = new GitRevisionPlugin();

module.exports = defineConfig({
    transpileDependencies: true,
    configureWebpack: {
        plugins: [
            new webpack.DefinePlugin({
                'process.env.VERSION': JSON.stringify(gitRevisionPlugin.version()),
                'process.env.COMMIT_HASH': JSON.stringify(gitRevisionPlugin.commithash()),
                'process.env.BRANCH': JSON.stringify(gitRevisionPlugin.branch())
            }),
        ],
    }
})
