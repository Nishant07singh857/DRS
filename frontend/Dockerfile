# Stage 1: Build the React application
# We use a Node.js image to build the app
FROM node:16-alpine as build

# Set the working directory inside the container
WORKDIR /app

# Copy package.json and package-lock.json first to leverage Docker caching
COPY package*.json ./

# Install all the dependencies
RUN npm install

# Copy the rest of the application code
COPY . .

# Build the production-ready static files
RUN npm run build

# Stage 2: Serve the application using a lightweight Nginx web server
# This creates a much smaller final image
FROM nginx:stable-alpine

# Copy the built static files from the build stage
COPY --from=build /app/build /usr/share/nginx/html

# Copy our custom Nginx configuration
# This is crucial for routing API requests to the backend
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80 for the web server
EXPOSE 80

# The command to start the Nginx server
CMD ["nginx", "-g", "daemon off;"]