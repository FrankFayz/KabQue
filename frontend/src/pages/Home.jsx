import Hero from '../components/home/Hero';
import HomeHowItWorks from '../components/home/HomeHowItWorks';
import HomeFeatures from '../components/home/HomeFeatures';
import HomeFooter from '../components/home/HomeFooter';

export default function Home() {
  return (
    <div className="home-page">
      <Hero />
      <HomeHowItWorks />
      <HomeFeatures />
      <HomeFooter />
    </div>
  );
}
