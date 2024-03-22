// index.js
import axios from 'axios';

const service = axios.create({
    baseURL: process.env.VUE_APP_BASE_URL, // 所有的请求地址前缀部分,
    timeout: 5000, // 请求超时时间
    withCredentials: true, // 异步请求携带cookie
    headers: {
        "Content-Type": "application/json;charset=UTF-8"
    }
});

service.defaults.referrerPolicy = 'no-referrer';

// 请求拦截器
service.interceptors.request.use(
  (config) => {
    // 在请求发送之前做一些处理，例如添加 token
    config.headers.Authorization = `Bearer ${localStorage.getItem('token')}`;
    return config;
  },
  (error) => {
    // 对请求错误做些什么
    console.log(error);
    return Promise.reject(error);
  }
);

// 异常拦截处理器
const errorHandler = (error) => {
    // 对响应错误做些什么
	console.log(error.response);

	if (error.message === 'Network Error') {
		console.error('系统异常')
	}
	if (error.response) {
        const data = error.response.data;
		// 从本地存储加载token
		const access_token = localStorage.getItem('access_token');

		if (error.response.status === 403) {
			console.error(data.msg)
			// eslint-disable-next-line no-mixed-spaces-and-tabs
    	}
		// 判断http状态是否是401
		if (error.response.status === 401) {
			// 调接口，刷新token
			error.config.headers.Authorization = access_token;
		}

	}
	return Promise.reject(error)
}

// 响应拦截器
service.interceptors.response.use(
  (response) => {
    // 对响应数据做一些处理
    return response.data;
  },
  errorHandler,
);

export default service;
